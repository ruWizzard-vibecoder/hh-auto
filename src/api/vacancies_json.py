"""JSON API for vacancies + applications (feeds the Next.js frontend)."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.application import Application
from src.models.company_rule import CompanyRule
from src.models.cover_letter import CoverLetter
from src.models.resume import Resume
from src.models.vacancy import Vacancy

router = APIRouter(prefix="/api")


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize_vacancy(v: Vacancy) -> dict[str, Any]:
    return {
        "id": v.id,
        "hh_id": v.hh_id,
        "title": v.title,
        "company_name": v.company_name,
        "url": v.url,
        "relevance_score": v.relevance_score,
        "salary_from": v.salary_from,
        "salary_to": v.salary_to,
        "salary_currency": v.salary_currency,
        "employment": v.employment,
        "schedule": v.schedule,
        "description": v.description,
        "matched_skills": v.matched_skills or [],
        "missing_skills": v.missing_skills or [],
        "status": v.status,
        "recommended_resume_id": v.recommended_resume_id,
        "published_at": _iso(v.published_at),
    }


async def _resume_names_map(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Resume))
    return {r.hh_id: r.short_name for r in result.scalars().all()}


# ────────────────────────────────────────────────────────────────────────────
# Vacancies list
# ────────────────────────────────────────────────────────────────────────────

@router.get("/vacancies")
async def list_vacancies(
    status: str | None = Query(None),
    employment: str | None = Query(None),
    q: str = Query(""),
    page: int = Query(0, ge=0),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    query = select(Vacancy)
    count_query = select(func.count(Vacancy.id))

    if q:
        flt = Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        query = query.where(flt)
        count_query = count_query.where(flt)
    if status:
        query = query.where(Vacancy.status == status)
        count_query = count_query.where(Vacancy.status == status)
    else:
        query = query.where(Vacancy.status.notin_(["archived", "skipped"]))
        count_query = count_query.where(Vacancy.status.notin_(["archived", "skipped"]))
    if employment:
        query = query.where(Vacancy.employment == employment)
        count_query = count_query.where(Vacancy.employment == employment)

    total = (await db.execute(count_query)).scalar_one()
    query = (
        query.order_by(Vacancy.relevance_score.desc().nullslast())
        .offset(page * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = list(result.scalars().all())

    # Employment counts (global)
    employment_counts: dict[str, int] = {}
    for emp in ["full", "part", "project"]:
        c = (await db.execute(
            select(func.count(Vacancy.id)).where(Vacancy.employment == emp)
        )).scalar_one()
        if c > 0:
            employment_counts[emp] = c

    resume_names = await _resume_names_map(db)

    return {
        "vacancies": [_serialize_vacancy(v) for v in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": (page + 1) * per_page < total,
        "employment_counts": employment_counts,
        "resume_names": resume_names,
    }


@router.post("/vacancies/{vacancy_id}/blacklist.json")
async def blacklist_vacancy(vacancy_id: int, db: AsyncSession = Depends(get_db)):
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if vacancy.company_name:
        rule = CompanyRule(
            rule_type="blacklist",
            match_type="company_name",
            match_value=vacancy.company_name,
            reason=f"Blacklisted from vacancy: {vacancy.title}",
        )
        db.add(rule)
    vacancy.status = "blacklisted"
    await db.commit()
    return {"status": "blacklisted", "company": vacancy.company_name}


@router.post("/vacancies/{vacancy_id}/generate-letter.json")
async def generate_letter(vacancy_id: int, db: AsyncSession = Depends(get_db)):
    """Trigger LLM cover letter generation for a vacancy."""
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy:
        return JSONResponse({"error": "not_found"}, status_code=404)

    from src.services.cover_letter_generator import (
        CoverLetterRejectedError,
        generate_cover_letter,
    )
    from src.services.pipeline import _load_resume_text
    from src.services.vacancy_scorer import ScoringResult

    resume_text = _load_resume_text()
    scoring = ScoringResult(
        score=vacancy.relevance_score or 0.5,
        reasoning=vacancy.score_reasoning or "",
        matched_skills=vacancy.matched_skills or [],
        missing_skills=vacancy.missing_skills or [],
    )
    try:
        draft = await generate_cover_letter(
            title=vacancy.title,
            company_name=vacancy.company_name,
            description=vacancy.description,
            key_skills=vacancy.key_skills,
            resume_text=resume_text,
            scoring=scoring,
        )
    except CoverLetterRejectedError as exc:
        return JSONResponse(
            {
                "error": "rejected_by_safety_check",
                "detail": str(exc),
                "hint": "Описание вакансии похоже на prompt injection. Письмо не сохранено — отклик без письма или ручная правка.",
            },
            status_code=422,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    letter = CoverLetter(
        vacancy_id=vacancy.id,
        generated_text=draft.text,
        generation_prompt=draft.prompt_used[:5000],
        model_used=draft.model,
        status="pending",
        resume_id=vacancy.recommended_resume_id,
    )
    db.add(letter)
    vacancy.status = "queued"
    await db.commit()
    return {"status": "ok", "cover_letter_id": letter.id}


# ────────────────────────────────────────────────────────────────────────────
# Applications list
# ────────────────────────────────────────────────────────────────────────────

@router.get("/applications.json")
async def list_applications(
    status: str | None = Query(None),
    q: str = Query(""),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    query = (
        select(Application)
        .options(selectinload(Application.vacancy))
        .order_by(Application.applied_at.desc().nullslast())
    )
    if status:
        query = query.where(Application.status == status)
    if q:
        query = query.join(Application.vacancy).where(
            Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        )
    query = query.limit(limit)
    result = await db.execute(query)
    apps = list(result.scalars().all())

    # Status counts (all statuses)
    counts: dict[str, int] = {}
    for s in ["sent", "viewed", "invited", "declined"]:
        c = (await db.execute(
            select(func.count(Application.id)).where(Application.status == s)
        )).scalar_one()
        counts[s] = c
    total = (await db.execute(select(func.count(Application.id)))).scalar_one()

    resume_names = await _resume_names_map(db)

    items = []
    for a in apps:
        items.append({
            "id": a.id,
            "status": a.status,
            "applied_at": _iso(a.applied_at),
            "applied_via": a.applied_via,
            "resume_id": a.resume_id,
            "vacancy": {
                "id": a.vacancy.id,
                "hh_id": a.vacancy.hh_id,
                "title": a.vacancy.title,
                "company_name": a.vacancy.company_name,
                "url": a.vacancy.url,
            } if a.vacancy else None,
        })

    return {
        "applications": items,
        "counts": counts,
        "total": total,
        "resume_names": resume_names,
    }
