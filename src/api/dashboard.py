"""Dashboard HTML routes (Jinja2 templates)."""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import Integer, select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.vacancy import Vacancy
from src.models.cover_letter import CoverLetter
from src.models.application import Application
from src.models.search_profile import SearchProfile
from src.models.company_rule import CompanyRule
from src.models.event_log import EventLog
from src.models.daily_summary import DailySummary
from src.models.resume import Resume
from src.services.hh_auth import is_authenticated

router = APIRouter()


def _templates():
    from src.main import templates
    return templates


async def _get_resume_names(db: AsyncSession) -> dict[str, str]:
    """Build {hh_id: short_name} dict for all resumes."""
    result = await db.execute(select(Resume))
    return {r.hh_id: r.short_name for r in result.scalars().all()}


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    t = _templates()

    # Gather stats
    total_vacancies = (await db.execute(select(func.count(Vacancy.id)))).scalar_one()
    pending_letters = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()
    applications_sent = (await db.execute(
        select(func.count(Application.id))
    )).scalar_one()

    from datetime import date
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

    stats = {
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

    return t.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "stats": stats,
        "pending_count": pending_letters,
    })


@router.get("/cover-letters")
async def cover_letters_page(
    request: Request,
    status: str | None = Query(None),
    employment: str | None = Query(None),
    sort: str = Query("date"),
    group: str | None = Query(None),
    q: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    t = _templates()

    query = select(CoverLetter).join(CoverLetter.vacancy).options(selectinload(CoverLetter.vacancy))
    if q:
        query = query.where(
            Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        )
    if status:
        query = query.where(CoverLetter.status == status)
    else:
        # Hide rejected from default view — only show when explicitly filtered
        query = query.where(CoverLetter.status != "rejected")
    if employment:
        query = query.where(Vacancy.employment == employment)
    if sort == "score":
        query = query.order_by(Vacancy.relevance_score.desc().nullslast())
    else:
        query = query.order_by(CoverLetter.generated_at.desc())
    query = query.limit(100)

    result = await db.execute(query)
    letters = list(result.scalars().all())

    # Counts
    counts = {}
    for s in ["pending", "approved", "no_letter", "sent", "rejected"]:
        c = (await db.execute(
            select(func.count(CoverLetter.id)).where(CoverLetter.status == s)
        )).scalar_one()
        counts[s] = c

    # Employment counts for filter badges (scoped to current status filter)
    employment_counts = {}
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
        c = (await db.execute(emp_q)).scalar_one()
        if c > 0:
            employment_counts[emp] = c

    pending_count = counts["pending"]

    # Group by company if requested
    grouped = None
    if group == "company":
        from collections import OrderedDict
        grouped = OrderedDict()
        for letter in letters:
            company = letter.vacancy.company_name or "Без компании"
            grouped.setdefault(company, []).append(letter)

    resume_names = await _get_resume_names(db)

    return t.TemplateResponse(request, "cover_letters.html", {
        "request": request,
        "letters": letters,
        "counts": counts,
        "current_status": status,
        "current_employment": employment,
        "current_sort": sort,
        "current_group": group,
        "current_search": q,
        "grouped": grouped,
        "employment_counts": employment_counts,
        "pending_count": pending_count,
        "resume_names": resume_names,
    })


@router.get("/vacancies")
async def vacancies_page(
    request: Request,
    status: str | None = Query(None),
    employment: str | None = Query(None),
    group: str | None = Query(None),
    page: int = Query(0, ge=0),
    q: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    t = _templates()
    per_page = 50

    query = select(Vacancy)
    count_query = select(func.count(Vacancy.id))
    if q:
        search_filter = Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    if status:
        query = query.where(Vacancy.status == status)
        count_query = count_query.where(Vacancy.status == status)
    else:
        # Hide archived and skipped from default view
        query = query.where(Vacancy.status.notin_(["archived", "skipped"]))
        count_query = count_query.where(Vacancy.status.notin_(["archived", "skipped"]))
    if employment:
        query = query.where(Vacancy.employment == employment)
        count_query = count_query.where(Vacancy.employment == employment)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Vacancy.relevance_score.desc().nullslast()).offset(
        page * per_page
    ).limit(per_page)

    result = await db.execute(query)
    vacancies = list(result.scalars().all())

    # Employment counts for filter badges
    employment_counts = {}
    for emp in ["full", "part", "project"]:
        c = (await db.execute(
            select(func.count(Vacancy.id)).where(Vacancy.employment == emp)
        )).scalar_one()
        if c > 0:
            employment_counts[emp] = c

    pending_count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()

    # Group by company if requested
    grouped = None
    if group == "company":
        from collections import OrderedDict
        grouped = OrderedDict()
        for v in vacancies:
            company = v.company_name or "Без компании"
            grouped.setdefault(company, []).append(v)

    resume_names = await _get_resume_names(db)

    return t.TemplateResponse(request, "vacancies.html", {
        "request": request,
        "vacancies": vacancies,
        "total": total,
        "current_status": status,
        "current_employment": employment,
        "current_group": group,
        "current_search": q,
        "grouped": grouped,
        "employment_counts": employment_counts,
        "page": page,
        "has_more": (page + 1) * per_page < total,
        "pending_count": pending_count,
        "resume_names": resume_names,
    })


@router.get("/applications")
async def applications_page(
    request: Request,
    status: str | None = Query(None),
    q: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    t = _templates()

    query = select(Application).join(Application.vacancy).options(selectinload(Application.vacancy))
    count_query = select(func.count(Application.id)).join(Application.vacancy)
    if q:
        search_filter = Vacancy.title.ilike(f"%{q}%") | Vacancy.company_name.ilike(f"%{q}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    if status:
        query = query.where(Application.status == status)
        count_query = count_query.where(Application.status == status)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Application.applied_at.desc()).limit(100)

    result = await db.execute(query)
    applications = list(result.scalars().all())

    pending_count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()

    resume_names = await _get_resume_names(db)

    return t.TemplateResponse(request, "applications.html", {
        "request": request,
        "applications": applications,
        "total": total,
        "current_status": status,
        "current_search": q,
        "pending_count": pending_count,
        "resume_names": resume_names,
    })


@router.get("/settings")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    t = _templates()

    auth_ok = await is_authenticated()

    profiles = list(
        (await db.execute(select(SearchProfile).order_by(SearchProfile.id))).scalars().all()
    )
    rules = list(
        (await db.execute(select(CompanyRule).where(CompanyRule.is_active == True))).scalars().all()
    )

    pending_count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()

    resumes = list(
        (await db.execute(select(Resume).order_by(Resume.rotation_priority))).scalars().all()
    )

    return t.TemplateResponse(request, "settings.html", {
        "request": request,
        "is_authenticated": auth_ok,
        "profiles": profiles,
        "rules": rules,
        "pending_count": pending_count,
        "resumes": resumes,
    })


@router.get("/analytics")
async def analytics_page(request: Request, db: AsyncSession = Depends(get_db)):
    t = _templates()

    total_vacancies = (await db.execute(select(func.count(Vacancy.id)))).scalar_one()
    applications_sent = (await db.execute(select(func.count(Application.id)))).scalar_one()
    invited = (await db.execute(
        select(func.count(Application.id)).where(Application.status == "invited")
    )).scalar_one()

    avg_score_result = (await db.execute(
        select(func.avg(Vacancy.relevance_score)).where(Vacancy.relevance_score.isnot(None))
    )).scalar_one()
    avg_score = avg_score_result or 0.0

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

    pending_count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()

    stats = {
        "total_vacancies": total_vacancies,
        "applications_sent": applications_sent,
        "response_rate": response_rate,
        "avg_score": avg_score,
        "invited": invited,
        "letters_approved": letters_approved,
    }

    # Daily stats (last 14 days)
    from datetime import date, timedelta
    daily_stats = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        day_filter = func.date(Application.applied_at) == d
        sent_count = (await db.execute(
            select(func.count(Application.id)).where(day_filter)
        )).scalar_one()
        viewed_count = (await db.execute(
            select(func.count(Application.id)).where(day_filter, Application.status == "viewed")
        )).scalar_one()
        invited_count = (await db.execute(
            select(func.count(Application.id)).where(day_filter, Application.status == "invited")
        )).scalar_one()
        declined_count = (await db.execute(
            select(func.count(Application.id)).where(day_filter, Application.status == "declined")
        )).scalar_one()
        if sent_count or viewed_count or invited_count or declined_count:
            daily_stats.append({
                "date": d.strftime("%d.%m"),
                "sent": sent_count,
                "viewed": viewed_count,
                "invited": invited_count,
                "declined": declined_count,
            })

    # Top companies (top 10 by application count)
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
        {"name": row[0], "count": row[1], "responses": row[2] or 0}
        for row in top_companies_result.all()
    ]

    # Score distribution (5 buckets)
    from sqlalchemy import case, and_
    score_distribution = []
    buckets = [(0, 0.2, "0–20%"), (0.2, 0.4, "20–40%"), (0.4, 0.6, "40–60%"), (0.6, 0.8, "60–80%"), (0.8, 1.01, "80–100%")]
    for low, high, label in buckets:
        bucket_filter = and_(
            Vacancy.relevance_score >= low,
            Vacancy.relevance_score < high,
        )
        total_count = (await db.execute(
            select(func.count(Vacancy.id)).where(bucket_filter)
        )).scalar_one()
        applied_count = (await db.execute(
            select(func.count(Vacancy.id)).where(bucket_filter, Vacancy.status == "applied")
        )).scalar_one()
        score_distribution.append({
            "range": label,
            "count": total_count,
            "applied": applied_count,
        })

    max_daily = max((d["sent"] for d in daily_stats), default=1) if daily_stats else 1

    return t.TemplateResponse(request, "analytics.html", {
        "request": request,
        "stats": stats,
        "daily_stats": daily_stats,
        "max_daily": max_daily,
        "top_companies": top_companies,
        "score_distribution": score_distribution,
        "pending_count": pending_count,
    })


@router.get("/summaries")
async def summaries_page(request: Request, db: AsyncSession = Depends(get_db)):
    t = _templates()

    result = await db.execute(
        select(DailySummary).order_by(DailySummary.summary_date.desc()).limit(30)
    )
    summaries = list(result.scalars().all())

    pending_count = (await db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
    )).scalar_one()

    return t.TemplateResponse(request, "summaries.html", {
        "request": request,
        "summaries": summaries,
        "pending_count": pending_count,
    })
