"""JSON variants of the dashboard/status/events endpoints.

These live alongside the HTML routes (dashboard.py, pipeline_api.py) and feed
the Next.js frontend at /workspace/hh-auto/web. The HTML routes stay in place
while the new frontend is being rolled out — once it's the default, the HTML
ones can be retired.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.application import Application
from src.models.cover_letter import CoverLetter
from src.models.event_log import EventLog
from src.models.vacancy import Vacancy
from src.services.hh_auth import is_authenticated

router = APIRouter(prefix="/api")


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict:
    total_vacancies = (await db.execute(select(func.count(Vacancy.id)))).scalar_one()
    pending_letters = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()
    applications_sent = (await db.execute(
        select(func.count(Application.id))
    )).scalar_one()
    applications_today = (await db.execute(
        select(func.count(Application.id)).where(
            func.date(Application.applied_at) == date.today()
        )
    )).scalar_one()
    viewed = (await db.execute(
        select(func.count(Application.id)).where(Application.status == "viewed")
    )).scalar_one()
    invited = (await db.execute(
        select(func.count(Application.id)).where(Application.status == "invited")
    )).scalar_one()
    scored = (await db.execute(
        select(func.count(Vacancy.id)).where(Vacancy.status != "discovered")
    )).scalar_one()
    letters_total = (await db.execute(select(func.count(CoverLetter.id)))).scalar_one()
    approved = (await db.execute(
        select(func.count(CoverLetter.id)).where(
            CoverLetter.status.in_(["approved", "edited", "sent", "no_letter"])
        )
    )).scalar_one()
    responded = (await db.execute(
        select(func.count(Application.id)).where(
            Application.status.in_(["viewed", "invited", "offer"])
        )
    )).scalar_one()

    return {
        "total_vacancies": total_vacancies,
        "pending_letters": pending_letters,
        "applications_sent": applications_sent,
        "applications_today": applications_today,
        "viewed": viewed,
        "invited": invited,
        "scored": scored,
        "letters_total": letters_total,
        "approved": approved,
        "responded": responded,
    }


@router.get("/cover-letters/pending-count")
async def cover_letters_pending_count(db: AsyncSession = Depends(get_db)) -> dict:
    count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()
    return {"count": count}


@router.get("/status.json")
async def status_json(db: AsyncSession = Depends(get_db)) -> dict:
    auth_ok = await is_authenticated()
    apps_today = (await db.execute(
        select(func.count(Application.id)).where(
            func.date(Application.applied_at) == func.current_date()
        )
    )).scalar_one()
    return {"authenticated": bool(auth_ok), "applications_today": apps_today}


@router.get("/events/recent.json")
async def events_recent_json(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(EventLog).order_by(EventLog.created_at.desc()).limit(30)
    )
    events = list(result.scalars().all())
    items = []
    for e in events:
        details = None
        if e.details and isinstance(e.details, dict):
            details = {k: v for k, v in list(e.details.items())[:5]}
        items.append({
            "id": e.id,
            "created_at": _iso(e.created_at),
            "event_type": e.event_type,
            "details": details,
            "error_message": e.error_message,
        })
    return {"events": items}


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
