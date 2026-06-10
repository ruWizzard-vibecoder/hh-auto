"""JSON API for analytics, summaries, settings — feeds the Next.js frontend."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.application import Application
from src.models.company_rule import CompanyRule
from src.models.cover_letter import CoverLetter
from src.models.daily_summary import DailySummary
from src.models.resume import Resume
from src.models.search_profile import SearchProfile
from src.models.vacancy import Vacancy
from src.services.hh_auth import is_authenticated

router = APIRouter(prefix="/api")


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ─── Analytics ────────────────────────────────────────────────────────────

@router.get("/analytics.json")
async def analytics_json(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    total_vacancies = (await db.execute(select(func.count(Vacancy.id)))).scalar_one()
    applications_sent = (await db.execute(select(func.count(Application.id)))).scalar_one()
    invited = (await db.execute(
        select(func.count(Application.id)).where(Application.status == "invited")
    )).scalar_one()
    avg_score = (await db.execute(
        select(func.avg(Vacancy.relevance_score)).where(Vacancy.relevance_score.isnot(None))
    )).scalar_one() or 0.0
    responded = (await db.execute(
        select(func.count(Application.id)).where(
            Application.status.in_(["viewed", "invited", "offer"])
        )
    )).scalar_one()
    response_rate = (responded / applications_sent * 100) if applications_sent > 0 else 0
    letters_approved = (await db.execute(
        select(func.count(CoverLetter.id)).where(
            CoverLetter.status.in_(["approved", "edited", "sent", "no_letter"])
        )
    )).scalar_one()

    stats = {
        "total_vacancies": total_vacancies,
        "applications_sent": applications_sent,
        "response_rate": response_rate,
        "avg_score": float(avg_score),
        "invited": invited,
        "letters_approved": letters_approved,
    }

    # Daily stats — last 14 days
    daily_stats = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        df = func.date(Application.applied_at) == d
        sent_count = (await db.execute(
            select(func.count(Application.id)).where(df)
        )).scalar_one()
        viewed_count = (await db.execute(
            select(func.count(Application.id)).where(df, Application.status == "viewed")
        )).scalar_one()
        invited_count = (await db.execute(
            select(func.count(Application.id)).where(df, Application.status == "invited")
        )).scalar_one()
        declined_count = (await db.execute(
            select(func.count(Application.id)).where(df, Application.status == "declined")
        )).scalar_one()
        daily_stats.append({
            "date": d.strftime("%d.%m"),
            "iso_date": d.isoformat(),
            "sent": sent_count,
            "viewed": viewed_count,
            "invited": invited_count,
            "declined": declined_count,
        })

    # Top companies
    top_companies_result = await db.execute(
        select(
            Vacancy.company_name,
            func.count(Application.id).label("cnt"),
            func.sum(
                func.cast(Application.status.in_(["viewed", "invited", "offer"]), Integer)
            ).label("responses"),
        )
        .join(Application.vacancy)
        .where(Vacancy.company_name.isnot(None))
        .group_by(Vacancy.company_name)
        .order_by(func.count(Application.id).desc())
        .limit(10)
    )
    top_companies = [
        {"name": row[0], "count": int(row[1]), "responses": int(row[2] or 0)}
        for row in top_companies_result.all()
    ]

    # Score distribution buckets
    score_distribution = []
    buckets = [
        (0.0, 0.2, "0–20%"),
        (0.2, 0.4, "20–40%"),
        (0.4, 0.6, "40–60%"),
        (0.6, 0.8, "60–80%"),
        (0.8, 1.01, "80–100%"),
    ]
    for low, high, label in buckets:
        bf = and_(Vacancy.relevance_score >= low, Vacancy.relevance_score < high)
        total = (await db.execute(select(func.count(Vacancy.id)).where(bf))).scalar_one()
        applied = (await db.execute(
            select(func.count(Vacancy.id)).where(bf, Vacancy.status == "applied")
        )).scalar_one()
        score_distribution.append({"range": label, "count": total, "applied": applied})

    return {
        "stats": stats,
        "daily_stats": daily_stats,
        "top_companies": top_companies,
        "score_distribution": score_distribution,
    }


# ─── Summaries ────────────────────────────────────────────────────────────

@router.get("/summaries.json")
async def summaries_json(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    result = await db.execute(
        select(DailySummary).order_by(DailySummary.summary_date.desc()).limit(30)
    )
    items = []
    for s in result.scalars().all():
        items.append({
            "id": s.id,
            "summary_date": s.summary_date.isoformat() if s.summary_date else None,
            "vacancies_discovered": s.vacancies_discovered,
            "applications_sent": s.applications_sent,
            "responses_received": s.responses_received,
            "avg_relevance_score": float(s.avg_relevance_score) if s.avg_relevance_score else None,
            "summary_text": s.summary_text,
            "top_vacancies": s.top_vacancies,
            "interview_prep": s.interview_prep,
            "insights": s.insights,
        })
    return {"summaries": items}


# ─── Settings ─────────────────────────────────────────────────────────────

@router.get("/settings.json")
async def settings_json(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    auth_ok = await is_authenticated()
    profiles = list((
        await db.execute(select(SearchProfile).order_by(SearchProfile.id))
    ).scalars().all())
    rules = list((
        await db.execute(select(CompanyRule).where(CompanyRule.is_active == True))  # noqa: E712
    ).scalars().all())
    resumes = list((
        await db.execute(select(Resume).order_by(Resume.rotation_priority))
    ).scalars().all())

    return {
        "is_authenticated": bool(auth_ok),
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "search_text": p.search_text,
                "area_id": p.area_id,
                "min_relevance_score": p.min_relevance_score,
                "resume_id": p.resume_id,
                "experience": p.experience,
                "employment": p.employment,
                "schedule": p.schedule,
                "salary_from": p.salary_from,
                "salary_to": p.salary_to,
                "only_with_salary": p.only_with_salary,
                "is_active": p.is_active,
            }
            for p in profiles
        ],
        "rules": [
            {
                "id": r.id,
                "rule_type": r.rule_type,
                "match_type": r.match_type,
                "match_value": r.match_value,
                "reason": r.reason,
            }
            for r in rules
        ],
        "resumes": [
            {
                "id": r.id,
                "hh_id": r.hh_id,
                "title": r.title,
                "short_name": r.short_name,
                "is_primary": r.is_primary,
                "visibility_status": r.visibility_status,
                "last_rotated_at": _iso(r.last_rotated_at),
                "rotation_priority": r.rotation_priority,
            }
            for r in resumes
        ],
    }
