"""Admin Gmail integration routes (§6.2): the durable OAuth "Connect Gmail"
flow so re-authorization is a one-time admin action instead of editing .env.

`/connect` and `/disconnect` and `/status` are ADMIN-only (bearer). `/callback`
is a browser redirect from Google and cannot carry a bearer — it is instead
verified by the signed `state` minted at `/connect` (CSRF defense).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.auth import require_roles
from app.core.errors import AuthenticationError, BadRequestError
from app.core.logging import get_logger
from app.core.responses import single
from app.integrations.gmail import client as gmail
from app.integrations.gmail import oauth
from app.models import User
from app.models.enums import UserRole

router = APIRouter(prefix="/integrations/gmail", tags=["integrations"])
log = get_logger("gmail")


@router.get("/status")
def gmail_status(admin: User = Depends(require_roles(UserRole.ADMIN))):
    """Connection status (no secrets): auth_mode, connected email, errors, backoff."""
    return single(gmail.get_status())


@router.get("/connect")
def gmail_connect(admin: User = Depends(require_roles(UserRole.ADMIN))):
    """Return the Google consent URL; the frontend redirects the browser to it."""
    if not oauth.oauth_client_configured():
        raise BadRequestError(
            "Gmail OAuth client is not configured",
            detail="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    return single({"authorization_url": oauth.authorization_url(str(admin.id))})


@router.get("/callback")
def gmail_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Google redirects here after consent. Verifies `state`, exchanges the code,
    stores tokens encrypted, then redirects back to the frontend admin page."""
    frontend = settings.frontend_base_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{frontend}/admin?gmail=error", status_code=302)
    try:
        tokens = oauth.exchange_code(code, state)
    except AuthenticationError:
        raise  # tampered/expired state → 401 envelope
    except Exception as exc:
        log.warning("gmail_callback_failed", error=str(exc))
        return RedirectResponse(f"{frontend}/admin?gmail=error", status_code=302)
    has_token = gmail.upsert_oauth_credentials(
        refresh_token=tokens["refresh_token"],
        access_token=tokens["access_token"],
        token_expiry=tokens["token_expiry"],
        connected_email=tokens["email"],
        scopes=tokens["scopes"],
    )
    if not has_token:
        # Google omitted the refresh token and none was stored before.
        log.warning("gmail_callback_no_refresh_token", email=tokens.get("email"))
        return RedirectResponse(f"{frontend}/admin?gmail=error&reason=no_refresh_token", status_code=302)
    log.info("gmail_connected", email=tokens.get("email"), auth_mode="oauth_db")
    return RedirectResponse(f"{frontend}/admin?gmail=connected", status_code=302)


@router.post("/disconnect")
def gmail_disconnect(admin: User = Depends(require_roles(UserRole.ADMIN))):
    """Clear stored OAuth tokens. Does not affect service-account / env modes."""
    gmail.disconnect()
    return single(gmail.get_status())
