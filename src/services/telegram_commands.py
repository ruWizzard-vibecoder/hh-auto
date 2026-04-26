"""Telegram bot command handlers (/stats, /pending, /approve, /reject)."""

import logging

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func

from src.config import settings
from src.database import async_session
from src.models.vacancy import Vacancy
from src.models.cover_letter import CoverLetter
from src.models.application import Application

logger = logging.getLogger("hh-auto.telegram.commands")

router = Router()


def _is_authorized(message: Message) -> bool:
    """Check if message is from the authorized chat."""
    return str(message.chat.id) == settings.telegram_chat_id


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _is_authorized(message):
        return

    async with async_session() as db:
        total_vacancies = (await db.execute(select(func.count(Vacancy.id)))).scalar_one()
        pending_letters = (await db.execute(
            select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
        )).scalar_one()
        approved_letters = (await db.execute(
            select(func.count(CoverLetter.id)).where(
                CoverLetter.status.in_(["approved", "edited"])
            )
        )).scalar_one()
        apps_total = (await db.execute(select(func.count(Application.id)))).scalar_one()
        apps_today = (await db.execute(
            select(func.count(Application.id)).where(
                func.date(Application.applied_at) == func.current_date()
            )
        )).scalar_one()
        invited = (await db.execute(
            select(func.count(Application.id)).where(Application.status == "invited")
        )).scalar_one()

    text = (
        "<b>hh-auto stats</b>\n\n"
        f"Vacancies: {total_vacancies}\n"
        f"Pending letters: {pending_letters}\n"
        f"Approved (ready): {approved_letters}\n"
        f"Applications total: {apps_total}\n"
        f"Applications today: {apps_today}\n"
        f"Invitations: {invited}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    if not _is_authorized(message):
        return

    async with async_session() as db:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(CoverLetter)
            .options(selectinload(CoverLetter.vacancy))
            .join(CoverLetter.vacancy)
            .where(CoverLetter.status == "pending")
            .order_by(Vacancy.relevance_score.desc().nullslast())
            .limit(5)
        )
        letters = list(result.scalars().all())

    if not letters:
        await message.answer("No pending letters.")
        return

    lines = ["<b>Pending letters (top 5):</b>\n"]
    for l in letters:
        v = l.vacancy
        score = f"{v.relevance_score * 100:.0f}%" if v.relevance_score else "?"
        lines.append(
            f"<b>#{l.id}</b> [{score}] {v.title}"
            f"{f' @ {v.company_name}' if v.company_name else ''}"
        )
    lines.append(f"\n/approve &lt;id&gt; | /reject &lt;id&gt;")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("approve"))
async def cmd_approve(message: Message):
    if not _is_authorized(message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /approve <letter_id>")
        return

    try:
        letter_id = int(args[1])
    except ValueError:
        await message.answer("Invalid letter ID.")
        return

    from datetime import datetime
    async with async_session() as db:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(CoverLetter)
            .options(selectinload(CoverLetter.vacancy))
            .where(CoverLetter.id == letter_id)
        )
        letter = result.scalar_one_or_none()
        if not letter:
            await message.answer(f"Letter #{letter_id} not found.")
            return
        if letter.status != "pending":
            await message.answer(f"Letter #{letter_id} is already {letter.status}.")
            return

        letter.status = "approved"
        letter.reviewed_at = datetime.utcnow()
        await db.commit()

        v = letter.vacancy
        score = f"{v.relevance_score * 100:.0f}%" if v.relevance_score else "?"
        await message.answer(
            f"Approved #{letter_id}: {v.title} [{score}]"
        )


@router.message(Command("reject"))
async def cmd_reject(message: Message):
    if not _is_authorized(message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /reject <letter_id>")
        return

    try:
        letter_id = int(args[1])
    except ValueError:
        await message.answer("Invalid letter ID.")
        return

    from datetime import datetime
    async with async_session() as db:
        result = await db.execute(
            select(CoverLetter).where(CoverLetter.id == letter_id)
        )
        letter = result.scalar_one_or_none()
        if not letter:
            await message.answer(f"Letter #{letter_id} not found.")
            return
        if letter.status != "pending":
            await message.answer(f"Letter #{letter_id} is already {letter.status}.")
            return

        letter.status = "rejected"
        letter.reviewed_at = datetime.utcnow()
        await db.commit()

        await message.answer(f"Rejected #{letter_id}.")


def setup_dispatcher() -> Dispatcher:
    """Create and configure the aiogram Dispatcher."""
    dp = Dispatcher()
    dp.include_router(router)
    return dp
