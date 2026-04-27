"""REST API for cover letter actions (approve/edit/reject/bulk)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.cover_letter import CoverLetter
from src.models.vacancy import Vacancy
from src.services import seed_expansion_queue

router = APIRouter(prefix="/api/cover-letters")


def _render_letter_card(letter: CoverLetter) -> str:
    """Render a single cover letter card as HTML (for HTMX swap)."""
    v = letter.vacancy
    score_class = (
        "score-high" if v.relevance_score and v.relevance_score >= 0.7
        else "score-medium" if v.relevance_score and v.relevance_score >= 0.5
        else "score-low"
    )
    score_pct = f"{v.relevance_score * 100:.0f}%" if v.relevance_score else "—"
    badge_class = f"badge-{letter.status}"

    text = letter.edited_text or letter.generated_text

    return f"""
    <div class="cover-letter-card" id="letter-{letter.id}">
        <header>
            <div>
                <strong>{v.title}</strong>
                {f' @ {v.company_name}' if v.company_name else ''}
                <br>
                <small>
                    Score: <span class="{score_class}">{score_pct}</span>
                    | <a href="{v.url}" target="_blank">hh.ru</a>
                </small>
            </div>
            <span class="badge {badge_class}">{letter.status}</span>
        </header>
        <div class="cover-letter-text">{text}</div>
    </div>
    """


@router.post("/{letter_id}/approve")
async def approve(letter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(CoverLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        return HTMLResponse("<p>Letter not found</p>", status_code=404)

    letter.status = "approved"
    letter.reviewed_at = datetime.utcnow()
    await db.commit()

    if letter.vacancy and letter.vacancy.hh_id:
        seed_expansion_queue.enqueue(letter.vacancy.hh_id)

    return HTMLResponse(_render_letter_card(letter))


@router.post("/{letter_id}/edit")
async def edit_and_approve(
    letter_id: int,
    edited_text: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(CoverLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        return HTMLResponse("<p>Letter not found</p>", status_code=404)

    letter.edited_text = edited_text
    letter.status = "approved"
    letter.reviewed_at = datetime.utcnow()
    await db.commit()

    if letter.vacancy and letter.vacancy.hh_id:
        seed_expansion_queue.enqueue(letter.vacancy.hh_id)

    return HTMLResponse(_render_letter_card(letter))


@router.post("/{letter_id}/no-letter")
async def no_letter(letter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(CoverLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        return HTMLResponse("<p>Letter not found</p>", status_code=404)

    letter.status = "no_letter"
    letter.reviewed_at = datetime.utcnow()
    await db.commit()

    return HTMLResponse(_render_letter_card(letter))


@router.post("/{letter_id}/reject")
async def reject(letter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(CoverLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        return HTMLResponse("<p>Letter not found</p>", status_code=404)

    letter.status = "rejected"
    letter.reviewed_at = datetime.utcnow()
    # Archive the associated vacancy so it disappears from main vacancy list too
    if letter.vacancy and letter.vacancy.status not in ("applied",):
        letter.vacancy.status = "archived"
    await db.commit()

    # Return empty string so HTMX removes the card from the list
    return HTMLResponse("")


@router.post("/bulk-approve")
async def bulk_approve(
    threshold: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Approve all pending letters where vacancy score >= threshold."""
    threshold_norm = threshold / 100.0
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
    now = datetime.utcnow()
    seed_hh_ids: list[str] = []
    for letter in letters:
        letter.status = "approved"
        letter.reviewed_at = now
        if letter.vacancy and letter.vacancy.hh_id:
            seed_hh_ids.append(letter.vacancy.hh_id)
    await db.commit()

    for hh_id in seed_hh_ids:
        seed_expansion_queue.enqueue(hh_id)

    return JSONResponse({"updated": len(letters)})


@router.post("/bulk-no-letter")
async def bulk_no_letter(
    threshold: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Apply without letter for all pending where vacancy score < threshold."""
    threshold_norm = threshold / 100.0
    result = await db.execute(
        select(CoverLetter)
        .join(CoverLetter.vacancy)
        .where(
            CoverLetter.status == "pending",
            Vacancy.relevance_score < threshold_norm,
        )
    )
    letters = list(result.scalars().all())
    now = datetime.utcnow()
    for letter in letters:
        letter.status = "no_letter"
        letter.reviewed_at = now
    await db.commit()
    return JSONResponse({"updated": len(letters)})


@router.post("/bulk-reject")
async def bulk_reject(
    threshold: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Reject all pending letters where vacancy score < threshold."""
    threshold_norm = threshold / 100.0
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
    now = datetime.utcnow()
    for letter in letters:
        letter.status = "rejected"
        letter.reviewed_at = now
        if letter.vacancy and letter.vacancy.status not in ("applied",):
            letter.vacancy.status = "archived"
    await db.commit()
    return JSONResponse({"updated": len(letters)})
