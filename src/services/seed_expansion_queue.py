"""In-memory queue + worker for expanding similar vacancies from approved letters.

When the user approves a cover letter, the source vacancy's hh_id is enqueued
here. A single background worker drains the queue, calls
`Pipeline.expand_from_seed(hh_id)` for each item, and throttles between calls
to keep hh.ru API load bounded.

A TTL-based dedup map skips seeds that have already been processed within the
configured cooldown window — this absorbs `bulk-approve` storms and repeated
approve/edit clicks on the same letter.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from src.config import settings
from src.database import async_session
from src.services.hh_browser import get_browser
from src.services.hh_client import HHClient
from src.services.pipeline import Pipeline

logger = logging.getLogger("hh-auto.seed_expansion_queue")

_queue: asyncio.Queue[str] | None = None
_worker_task: asyncio.Task | None = None
_recent_seeds: dict[str, datetime] = {}


def _cooldown_active(hh_id: str) -> bool:
    """Return True if this seed was processed within the cooldown window."""
    last = _recent_seeds.get(hh_id)
    if not last:
        return False
    cutoff = datetime.utcnow() - timedelta(hours=settings.expansion_seed_cooldown_hours)
    if last < cutoff:
        _recent_seeds.pop(hh_id, None)
        return False
    return True


def _gc_recent_seeds():
    """Drop entries older than the cooldown window. Called opportunistically."""
    cutoff = datetime.utcnow() - timedelta(hours=settings.expansion_seed_cooldown_hours)
    stale = [k for k, v in _recent_seeds.items() if v < cutoff]
    for k in stale:
        _recent_seeds.pop(k, None)


def enqueue(hh_id: str) -> bool:
    """Enqueue a seed vacancy hh_id for similar-vacancies expansion.

    Returns False if the feature is disabled, the queue isn't running, the
    seed is in cooldown, or the queue is full. Producer never blocks.
    """
    if not settings.expansion_on_approve:
        return False
    if _queue is None:
        logger.warning(f"Seed queue not running, dropping {hh_id}")
        return False
    if _cooldown_active(hh_id):
        logger.debug(f"Seed {hh_id} in cooldown, skipping enqueue")
        return False
    try:
        _queue.put_nowait(hh_id)
    except asyncio.QueueFull:
        logger.warning(f"Seed queue full, dropping {hh_id}")
        return False
    logger.info(f"Enqueued seed {hh_id} (queue size now {_queue.qsize()})")
    return True


async def _worker():
    """Drain the queue one seed at a time, throttled between items."""
    assert _queue is not None
    logger.info(
        f"Seed expansion worker started "
        f"(throttle={settings.expansion_worker_throttle_seconds}s, "
        f"cooldown={settings.expansion_seed_cooldown_hours}h)"
    )
    while True:
        try:
            hh_id = await _queue.get()
        except asyncio.CancelledError:
            logger.info("Seed expansion worker cancelled")
            raise

        try:
            if _cooldown_active(hh_id):
                logger.debug(f"Worker: {hh_id} hit cooldown between enqueue and dequeue")
                continue

            await _expand_one(hh_id)
            _recent_seeds[hh_id] = datetime.utcnow()
            _gc_recent_seeds()
        except Exception as e:
            logger.error(f"Seed expansion worker error for {hh_id}: {e}", exc_info=True)
        finally:
            _queue.task_done()

        try:
            await asyncio.sleep(settings.expansion_worker_throttle_seconds)
        except asyncio.CancelledError:
            logger.info("Seed expansion worker cancelled during throttle")
            raise


async def _expand_one(hh_id: str):
    """Run a single expand_from_seed call with a fresh DB session and HH client."""
    async with async_session() as session:
        client = HHClient()
        try:
            pipeline = Pipeline(session, client, get_browser())
            await pipeline.expand_from_seed(
                hh_id, per_seed=settings.expansion_on_approve_per_seed
            )
        finally:
            await client.close()


def start_worker():
    """Start the singleton worker task. Idempotent."""
    global _queue, _worker_task
    if _worker_task and not _worker_task.done():
        return
    _queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_worker(), name="seed-expansion-worker")


async def stop_worker():
    """Cancel the worker and clear queue state. Safe to call if not running."""
    global _queue, _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
    _queue = None
    _recent_seeds.clear()
