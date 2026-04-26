"""Telegram notifications for new matches and status updates."""

import logging

from src.config import settings

logger = logging.getLogger("hh-auto.telegram")


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self._bot = None

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def _get_bot(self):
        if self._bot is None:
            if not self.is_configured:
                return None
            from aiogram import Bot
            from aiogram.client.session.aiohttp import AiohttpSession
            from aiohttp import BasicAuth
            # Telegram API blocked from Russian IPs — route through SOCKS5 proxy
            session = AiohttpSession(proxy="socks5://ssh-proxy:10808")
            self._bot = Bot(token=self.token, session=session)
        return self._bot

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat."""
        bot = await self._get_bot()
        if not bot:
            logger.debug("Telegram not configured, skipping notification")
            return False
        try:
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def notify_new_match(
        self,
        vacancy_title: str,
        company_name: str | None,
        score: float,
        vacancy_url: str,
        letter_preview: str,
    ):
        """Notify about a new matching vacancy with generated cover letter."""
        score_pct = f"{score * 100:.0f}%"
        company = company_name or "Unknown"
        preview = letter_preview[:200] + "..." if len(letter_preview) > 200 else letter_preview

        text = (
            f"<b>New match: {vacancy_title}</b>\n"
            f"Company: {company}\n"
            f"Score: {score_pct}\n"
            f"<a href=\"{vacancy_url}\">View on hh.ru</a>\n\n"
            f"<i>Cover letter preview:</i>\n"
            f"<pre>{preview}</pre>\n\n"
            f"Review at dashboard: /cover-letters"
        )
        await self.send_message(text)

    async def notify_status_change(
        self,
        vacancy_title: str,
        company_name: str | None,
        old_status: str,
        new_status: str,
    ):
        """Notify about application status change."""
        company = company_name or "Unknown"
        emoji = {"invited": "!!!!", "offer": "!!!!", "viewed": "", "declined": ""}.get(
            new_status, ""
        )

        text = (
            f"{emoji} <b>Status update</b>\n"
            f"{vacancy_title} @ {company}\n"
            f"{old_status} -> <b>{new_status}</b>"
        )
        await self.send_message(text)

    async def notify_search_complete(
        self, new_vacancies: int, letters_generated: int, pending_review: int
    ):
        """Notify about search cycle completion."""
        if letters_generated == 0:
            return  # Don't spam when nothing new

        text = (
            f"Search complete:\n"
            f"- {new_vacancies} new vacancies\n"
            f"- {letters_generated} letters generated\n"
            f"- {pending_review} pending review\n\n"
            f"Review at dashboard: /cover-letters"
        )
        await self.send_message(text)

    async def start_polling(self):
        """Start the bot in polling mode for command handling."""
        bot = await self._get_bot()
        if not bot:
            logger.info("Telegram not configured, skipping bot polling")
            return
        try:
            from src.services.telegram_commands import setup_dispatcher
            dp = setup_dispatcher()
            logger.info("Starting Telegram bot polling")
            await dp.start_polling(bot)
        except Exception as e:
            logger.error(f"Telegram polling failed: {e}")

    async def close(self):
        if self._bot:
            session = await self._bot.get_session()
            if session:
                await session.close()


# Singleton
notifier = TelegramNotifier()
