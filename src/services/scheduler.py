"""APScheduler job orchestration."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.database import async_session
from src.services.hh_client import HHClient
from src.services.hh_browser import get_browser
from src.services.hh_auth import ensure_logged_in
from src.services.pipeline import Pipeline

logger = logging.getLogger("hh-auto.scheduler")

scheduler = AsyncIOScheduler()


async def _get_pipeline(db):
    """Create Pipeline with public API client + shared browser."""
    client = HHClient()
    browser = get_browser()
    return Pipeline(db, client, browser), client


async def _run_search_cycle():
    logger.info("Scheduler: starting search cycle")
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_search_cycle()
        except Exception as e:
            logger.error(f"Search cycle failed: {e}")
        finally:
            await client.close()


async def _run_apply_cycle():
    logger.info("Scheduler: starting apply cycle")
    if not await ensure_logged_in():
        logger.warning("Scheduler: not logged in to hh.ru, skipping apply cycle")
        return
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_apply_cycle()
        except Exception as e:
            logger.error(f"Apply cycle failed: {e}")
        finally:
            await client.close()


async def _run_status_check():
    logger.info("Scheduler: starting status check")
    if not await ensure_logged_in():
        logger.warning("Scheduler: not logged in to hh.ru, skipping status check")
        return
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_status_check()
        except Exception as e:
            logger.error(f"Status check failed: {e}")
        finally:
            await client.close()


async def _run_resume_touch():
    logger.info("Scheduler: touching resumes")
    if not await ensure_logged_in():
        logger.warning("Scheduler: not logged in to hh.ru, skipping resume touch")
        return
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_resume_touch()
        except Exception as e:
            logger.error(f"Resume touch failed: {e}")
        finally:
            await client.close()


async def _run_archive_check():
    logger.info("Scheduler: starting archive check")
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_archive_check()
        except Exception as e:
            logger.error(f"Archive check failed: {e}")
        finally:
            await client.close()


async def _run_similar_expansion():
    logger.info("Scheduler: starting similar expansion")
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_similar_expansion()
        except Exception as e:
            logger.error(f"Similar expansion failed: {e}")
        finally:
            await client.close()


async def _run_resume_rotation():
    logger.info("Scheduler: starting resume rotation")
    if not await ensure_logged_in():
        logger.warning("Scheduler: not logged in to hh.ru, skipping resume rotation")
        return
    async with async_session() as db:
        pipeline, client = await _get_pipeline(db)
        try:
            await pipeline.run_resume_rotation()
        except Exception as e:
            logger.error(f"Resume rotation failed: {e}")
        finally:
            await client.close()


async def _run_daily_summary():
    logger.info("Scheduler: generating daily summary")
    async with async_session() as db:
        try:
            from src.services.daily_summary import (
                generate_daily_summary,
                format_summary_for_telegram,
            )
            summary = await generate_daily_summary(db)
            if summary:
                from src.services.telegram_bot import notifier
                if notifier.is_configured:
                    text = format_summary_for_telegram(summary)
                    await notifier.send_message(text)
                    logger.info("Daily summary sent to Telegram")
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")


def setup_scheduler():
    """Register all scheduled jobs."""
    scheduler.add_job(
        _run_search_cycle,
        IntervalTrigger(hours=settings.search_interval_hours),
        id="search_cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_apply_cycle,
        IntervalTrigger(minutes=settings.apply_interval_minutes),
        id="apply_cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_status_check,
        IntervalTrigger(hours=settings.status_check_interval_hours),
        id="status_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_resume_touch,
        IntervalTrigger(hours=4),
        id="resume_touch",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_archive_check,
        IntervalTrigger(hours=12),
        id="archive_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_similar_expansion,
        IntervalTrigger(hours=24),
        id="similar_expansion",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_resume_rotation,
        IntervalTrigger(days=10),
        id="resume_rotation",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_daily_summary,
        CronTrigger(hour=22, minute=0),  # Every day at 22:00
        id="daily_summary",
        replace_existing=True,
    )
    logger.info(
        f"Scheduler configured: search every {settings.search_interval_hours}h, "
        f"apply every {settings.apply_interval_minutes}min, "
        f"status check every {settings.status_check_interval_hours}h, "
        f"resume rotation every 10d, similar expansion every 24h, daily summary at 22:00"
    )
