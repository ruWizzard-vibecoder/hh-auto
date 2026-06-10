"""JSON API for cover letters (the new Next.js frontend).

Lives in parallel to src/api/cover_letters.py (which returns HTML for the
legacy Jinja UI). Once the new UI fully replaces the old one, the HTML
variants can be retired and these JSON endpoints become the only API.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.cover_letter import CoverLetter
from src.models.resume import Resume
from src.models.vacancy import Vacancy
from src.services import seed_expansion_queue

router = APIRouter(prefix="/api/letters")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize_letter(letter: CoverLetter) -> dict[str, Any]:
    v = letter.vacancy
    return {
        "id": letter.id,
        "status": letter.status,
        "generated_text": letter.generated_text,
        "edited_text": letter.edited_text,
        "resume_id": letter.resume_id,
        "generated_at": _iso(letter.generated_at),
        "reviewed_at": _iso(letter.reviewed_at),
        "vacancy": {
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
        },
    }


async def _resume_names_map(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Resume))
    return {r.hh_id: r.short_name for r in result.scalars().all()}


# ────────────────────────────────────────────────────────────────────────────
# List + counts
# ────────────────────────────────────────────────────────────────────────────

@router.get("")
async def list_letters(
    status: str | None = Query(None),
    employment: str | None = Query(None),
    sort: str = Query("date"),
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    query = (
        select(CoverLetter)
        .join(CoverLetter.vacancy)
        .options(selectinload(CoverLetter.vacancy))
    )
    if q:
        query = query.where(
            Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        )
    if status:
        query = query.where(CoverLetter.status == status)
    else:
        # Hide rejected from the default view (same logic as the Jinja page).
        query = query.where(CoverLetter.status != "rejected")
    if employment:
        query = query.where(Vacancy.employment == employment)

    if sort == "score":
        query = query.order_by(Vacancy.relevance_score.desc().nullslast())
    else:
        query = query.order_by(CoverLetter.generated_at.desc())

    query = query.limit(limit)
    result = await db.execute(query)
    letters = list(result.scalars().all())

    # Status counts (always full — independent of current filter).
    counts: dict[str, int] = {}
    for s in ["pending", "approved", "no_letter", "sent", "rejected"]:
        c = (await db.execute(
            select(func.count(CoverLetter.id)).where(CoverLetter.status == s)
        )).scalar_one()
        counts[s] = c

    # Employment counts (scoped to current status filter).
    employment_counts: dict[str, int] = {}
    for emp in ["full", "part", "project"]:
        emp_q = (
            select(func.count(CoverLetter.id))
            .join(CoverLetter.vacancy)
            .where(Vacancy.employment == emp)
        )
        if status:
            emp_q = emp_q.where(CoverLetter.status == status)
        else:
            emp_q = emp_q.where(CoverLetter.status != "rejected")
        emp_count = (await db.execute(emp_q)).scalar_one()
        if emp_count > 0:
            employment_counts[emp] = emp_count

    resume_names = await _resume_names_map(db)

    return {
        "letters": [_serialize_letter(l) for l in letters],
        "counts": counts,
        "employment_counts": employment_counts,
        "resume_names": resume_names,
        "total_returned": len(letters),
    }


# ────────────────────────────────────────────────────────────────────────────
# Single-letter actions — JSON variants
# ────────────────────────────────────────────────────────────────────────────

async def _load_letter(letter_id: int, db: AsyncSession) -> CoverLetter | None:
    result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(CoverLetter.id == letter_id)
    )
    return result.scalar_one_or_none()


@router.post("/{letter_id}/approve")
async def approve(letter_id: int, db: AsyncSession = Depends(get_db)):
    letter = await _load_letter(letter_id, db)
    if not letter:
        return JSONResponse({"error": "not_found"}, status_code=404)
    letter.status = "approved"
    letter.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    if letter.vacancy and letter.vacancy.hh_id:
        seed_expansion_queue.enqueue(letter.vacancy.hh_id)
    return _serialize_letter(letter)


class EditPayload(BaseModel):
    edited_text: str


@router.post("/{letter_id}/edit")
async def edit_and_approve(
    letter_id: int,
    payload: EditPayload,
    db: AsyncSession = Depends(get_db),
):
    letter = await _load_letter(letter_id, db)
    if not letter:
        return JSONResponse({"error": "not_found"}, status_code=404)
    letter.edited_text = payload.edited_text
    letter.status = "approved"
    letter.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    if letter.vacancy and letter.vacancy.hh_id:
        seed_expansion_queue.enqueue(letter.vacancy.hh_id)
    return _serialize_letter(letter)


@router.post("/{letter_id}/no-letter")
async def no_letter(letter_id: int, db: AsyncSession = Depends(get_db)):
    letter = await _load_letter(letter_id, db)
    if not letter:
        return JSONResponse({"error": "not_found"}, status_code=404)
    letter.status = "no_letter"
    letter.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return _serialize_letter(letter)


@router.post("/{letter_id}/reject")
async def reject(letter_id: int, db: AsyncSession = Depends(get_db)):
    letter = await _load_letter(letter_id, db)
    if not letter:
        return JSONResponse({"error": "not_found"}, status_code=404)
    letter.status = "rejected"
    letter.reviewed_at = datetime.now(timezone.utc)
    if letter.vacancy and letter.vacancy.status not in ("applied",):
        letter.vacancy.status = "archived"
    await db.commit()
    return _serialize_letter(letter)


# ────────────────────────────────────────────────────────────────────────────
# Bulk actions
# ────────────────────────────────────────────────────────────────────────────

class BulkPayload(BaseModel):
    threshold: float  # 0..100


@router.post("/bulk-approve")
async def bulk_approve(payload: BulkPayload, db: AsyncSession = Depends(get_db)):
    threshold_norm = payload.threshold / 100.0
    result = await db.execute(
        select(CoverLetter)
        .join(CoverLetter.vacancy)
        .options(selectinload(CoverLetter.vacancy))
        .where(
            CoverLetter.status == "pending",
            Vacancy.relevance_score >= threshold_norm,
        )
    )
    letters = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    seed_hh_ids: list[str] = []
    for letter in letters:
        letter.status = "approved"
        letter.reviewed_at = now
        if letter.vacancy and letter.vacancy.hh_id:
            seed_hh_ids.append(letter.vacancy.hh_id)
    await db.commit()
    for hh_id in seed_hh_ids:
        seed_expansion_queue.enqueue(hh_id)
    return {"updated": len(letters)}


@router.post("/bulk-no-letter")
async def bulk_no_letter(payload: BulkPayload, db: AsyncSession = Depends(get_db)):
    threshold_norm = payload.threshold / 100.0
    result = await db.execute(
        select(CoverLetter)
        .join(CoverLetter.vacancy)
        .where(
            CoverLetter.status == "pending",
            Vacancy.relevance_score < threshold_norm,
        )
    )
    letters = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for letter in letters:
        letter.status = "no_letter"
        letter.reviewed_at = now
    await db.commit()
    return {"updated": len(letters)}


@router.post("/bulk-reject")
async def bulk_reject(payload: BulkPayload, db: AsyncSession = Depends(get_db)):
    threshold_norm = payload.threshold / 100.0
    result = await db.execute(
        select(CoverLetter)
        .join(CoverLetter.vacancy)
        .options(selectinload(CoverLetter.vacancy))
        .where(
            CoverLetter.status == "pending",
            Vacancy.relevance_score < threshold_norm,
        )
    )
    letters = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for letter in letters:
        letter.status = "rejected"
        letter.reviewed_at = now
        if letter.vacancy and letter.vacancy.status not in ("applied",):
            letter.vacancy.status = "archived"
    await db.commit()
    return {"updated": len(letters)}
