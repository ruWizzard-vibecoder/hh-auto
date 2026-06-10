"""REST API for manual pipeline triggers and status."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, async_session
from src.models.event_log import EventLog
from src.models.vacancy import Vacancy
from src.models.application import Application
from src.models.cover_letter import CoverLetter
from src.services.hh_client import HHClient
from src.services.hh_browser import get_browser
from src.services.hh_auth import ensure_logged_in
from src.services.pipeline import Pipeline

logger = logging.getLogger("hh-auto.pipeline_api")

router = APIRouter(prefix="/api")


@router.post("/pipeline/search")
async def trigger_search(db: AsyncSession = Depends(get_db)):
    """Manually trigger search cycle (runs in background)."""
    async def _run():
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_search_cycle()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "search_started"})


@router.post("/pipeline/apply")
async def trigger_apply(db: AsyncSession = Depends(get_db)):
    """Manually trigger apply cycle."""
    async def _run():
        if not await ensure_logged_in():
            logger.warning("Not logged in to hh.ru, cannot apply")
            return
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_apply_cycle()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "apply_started"})


@router.post("/pipeline/status-check")
async def trigger_status_check(db: AsyncSession = Depends(get_db)):
    """Manually trigger status check."""
    async def _run():
        if not await ensure_logged_in():
            logger.warning("Not logged in to hh.ru, cannot check statuses")
            return
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_status_check()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "status_check_started"})


@router.post("/pipeline/resume-touch")
async def trigger_resume_touch(db: AsyncSession = Depends(get_db)):
    """Manually trigger resume touch for all resumes."""
    async def _run():
        if not await ensure_logged_in():
            logger.warning("Not logged in to hh.ru, cannot touch resumes")
            return
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_resume_touch()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "resume_touch_started"})


@router.post("/pipeline/archive-check")
async def trigger_archive_check(db: AsyncSession = Depends(get_db)):
    """Manually trigger archive check for pending vacancies."""
    async def _run():
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_archive_check()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "archive_check_started"})


@router.post("/pipeline/similar-expansion")
async def trigger_similar_expansion(db: AsyncSession = Depends(get_db)):
    """Manually trigger similar vacancies expansion (hh.ru recommendations)."""
    async def _run():
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_similar_expansion()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "similar_expansion_started"})


@router.post("/pipeline/rescore")
async def trigger_rescore(db: AsyncSession = Depends(get_db)):
    """Rescore vacancies that got fallback 0.5 due to AI failure."""
    from sqlalchemy import and_
    from src.models.vacancy import Vacancy
    from src.services.vacancy_scorer import ai_score
    from src.services.pipeline import _load_resume_text

    async def _run():
        resume_text = _load_resume_text()
        async with async_session() as session:
            result = await session.execute(
                select(Vacancy).where(
                    and_(
                        Vacancy.status == "scored",
                        Vacancy.relevance_score == 0.5,
                        Vacancy.score_reasoning.like("AI scoring failed%"),
                    )
                ).order_by(Vacancy.id)
            )
            vacancies = list(result.scalars().all())
            logger.info(f"Rescore: {len(vacancies)} vacancies to process")

            rescored = 0
            errors = 0
            for i, v in enumerate(vacancies):
                try:
                    ai_result = await ai_score(
                        title=v.title,
                        company_name=v.company_name,
                        description=v.description or "",
                        key_skills=v.key_skills or [],
                        resume_text=resume_text,
                    )
                    v.relevance_score = ai_result.score
                    v.score_reasoning = ai_result.reasoning
                    v.matched_skills = ai_result.matched_skills
                    v.missing_skills = ai_result.missing_skills
                    rescored += 1

                    if (i + 1) % 5 == 0:
                        await session.commit()
                        logger.info(
                            f"Rescore progress: {i+1}/{len(vacancies)}, "
                            f"rescored={rescored}, errors={errors}"
                        )
                except Exception as e:
                    errors += 1
                    logger.error(f"Rescore error [{i+1}] {v.title}: {e}")
                    import asyncio as aio
                    await aio.sleep(1)

            await session.commit()
            logger.info(
                f"Rescore complete: {rescored}/{len(vacancies)} rescored, "
                f"{errors} errors"
            )

    asyncio.create_task(_run())
    return JSONResponse({"status": "rescore_started"})


@router.get("/status")
async def service_status(db: AsyncSession = Depends(get_db)):
    """Quick status text for footer."""
    from src.services.hh_auth import is_authenticated
    auth_ok = await is_authenticated()
    apps_today_result = await db.execute(
        select(func.count(Application.id)).where(
            func.date(Application.applied_at) == func.current_date()
        )
    )
    apps_today = apps_today_result.scalar_one()

    auth_str = "hh.ru: подключено" if auth_ok else "hh.ru: не подключено"
    return f"{auth_str} | Сегодня: {apps_today} откликов"


@router.get("/events/recent")
async def recent_events(db: AsyncSession = Depends(get_db)):
    """Return recent events as HTML table."""
    result = await db.execute(
        select(EventLog).order_by(EventLog.created_at.desc()).limit(20)
    )
    events = list(result.scalars().all())

    if not events:
        return (
            '<p class="text-muted" '
            'style="font-family: var(--mono); letter-spacing: .1em; '
            'text-transform: uppercase; font-size: 11px; padding: 16px 0;">'
            '···  событий пока нет — запустите поиск  ···'
            '</p>'
        )

    items = ""
    for e in events:
        time_str = e.created_at.strftime("%d.%m %H:%M") if e.created_at else "—"
        details = ""
        if e.details:
            if isinstance(e.details, dict):
                details = " · ".join(f"{k} {v}" for k, v in list(e.details.items())[:3])
        error_str = f' <small class="text-danger">{e.error_message[:60]}</small>' if e.error_message else ""
        details_str = f' — <span class="text-muted">{details}</span>' if details else ""
        items += (
            f'<div class="timeline-item">'
            f'<div class="timeline-dot"></div>'
            f'<div class="timeline-content">'
            f'<span class="timeline-time">{time_str}</span>'
            f'<strong>{e.event_type}</strong>'
            f'{details_str}{error_str}'
            f'</div></div>'
        )

    return f'<div class="timeline">{items}</div>'


@router.post("/vacancies/{vacancy_id}/blacklist")
async def blacklist_vacancy(vacancy_id: int, db: AsyncSession = Depends(get_db)):
    """Blacklist the company of a vacancy."""
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy:
        return JSONResponse({"error": "not found"}, status_code=404)

    if vacancy.company_name:
        from src.models.company_rule import CompanyRule
        rule = CompanyRule(
            rule_type="blacklist",
            match_type="company_name",
            match_value=vacancy.company_name,
            reason=f"Blacklisted from vacancy: {vacancy.title}",
        )
        db.add(rule)

    vacancy.status = "blacklisted"
    await db.commit()
    return JSONResponse({"status": "blacklisted", "company": vacancy.company_name})


@router.post("/vacancies/{vacancy_id}/generate-letter")
async def generate_letter_for_vacancy(vacancy_id: int, db: AsyncSession = Depends(get_db)):
    """Manually generate a cover letter for a specific vacancy."""
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy:
        return JSONResponse({"error": "not found"}, status_code=404)

    from src.services.cover_letter_generator import (
        CoverLetterRejectedError,
        generate_cover_letter,
    )
    from src.services.vacancy_scorer import ScoringResult
    from src.services.pipeline import _load_resume_text

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

        # Match best resume for this vacancy
        from src.services.resume_matcher import match_resume
        match = await match_resume(
            db,
            vacancy_title=vacancy.title,
            vacancy_skills=vacancy.key_skills,
            vacancy_description=vacancy.description,
        )
        resume_id = match.resume_hh_id if match else ""

        # Update vacancy with recommended resume
        if match and not vacancy.recommended_resume_id:
            vacancy.recommended_resume_id = match.resume_hh_id

        letter = CoverLetter(
            vacancy_id=vacancy.id,
            resume_id=resume_id,
            generated_text=draft.text,
            generation_prompt=draft.prompt_used[:5000],
            model_used=draft.model,
            status="pending",
        )
        db.add(letter)
        vacancy.status = "queued"
        await db.commit()

        return JSONResponse({"status": "generated", "letter_id": letter.id})
    except CoverLetterRejectedError as e:
        return JSONResponse(
            {
                "error": "rejected_by_safety_check",
                "detail": str(e),
                "hint": "Описание вакансии похоже на prompt injection. Письмо не сохранено.",
            },
            status_code=422,
        )
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@router.post("/summaries/generate")
async def generate_summary_now(db: AsyncSession = Depends(get_db)):
    """Manually generate today's daily summary."""
    from src.services.daily_summary import generate_daily_summary

    async def _run():
        async with async_session() as session:
            try:
                summary = await generate_daily_summary(session)
                if summary:
                    # Send to Telegram
                    from src.services.daily_summary import format_summary_for_telegram
                    from src.services.telegram_bot import notifier
                    if notifier.is_configured:
                        text = format_summary_for_telegram(summary)
                        await notifier.send_message(text)
            except Exception as e:
                logger.error(f"Manual summary generation failed: {e}")

    asyncio.create_task(_run())
    return JSONResponse({"status": "summary_generation_started"})
