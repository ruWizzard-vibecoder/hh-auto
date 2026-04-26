"""Browser-based authentication routes for hh.ru."""

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from src.services.hh_auth import login, is_authenticated

router = APIRouter(prefix="/auth")


@router.post("/login")
async def do_login(
    email: str = Form(""),
    password: str = Form(""),
):
    """Login to hh.ru via browser with email/password."""
    if not email or not password:
        return RedirectResponse(url="/settings?error=credentials_required", status_code=303)

    success = await login(email, password)
    if success:
        return RedirectResponse(url="/settings?success=auth", status_code=303)
    else:
        return RedirectResponse(url="/settings?error=login_failed", status_code=303)


@router.get("/status")
async def auth_status():
    """Check if browser is logged in to hh.ru."""
    return {"authenticated": await is_authenticated()}
