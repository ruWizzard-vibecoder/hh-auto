"""Browser-based authentication for hh.ru."""

import logging

from src.config import settings
from src.services.hh_browser import get_browser

logger = logging.getLogger("hh-auto.hh_auth")


async def is_authenticated() -> bool:
    """Check if browser has saved login state."""
    browser = get_browser()
    return browser.is_logged_in()


async def login(email: str, password: str) -> bool:
    """Login to hh.ru via browser. Returns True on success."""
    browser = get_browser()
    return await browser.login(email, password)


async def ensure_logged_in() -> bool:
    """Ensure browser is logged in, attempt login from config if not."""
    if await is_authenticated():
        return True

    if not settings.hh_email or not settings.hh_password:
        logger.warning("No hh.ru credentials configured")
        return False

    logger.info("Attempting auto-login with configured credentials")
    return await login(settings.hh_email, settings.hh_password)
