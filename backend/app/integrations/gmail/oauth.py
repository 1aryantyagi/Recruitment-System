"""OAuth 2.0 "Connect Gmail" web-flow helpers (Path B).

Builds the Google consent URL, validates the signed `state` on callback (CSRF
defense — the browser redirect can't carry a bearer token), and exchanges the
authorization code for tokens. Persistence lives in `client.upsert_oauth_credentials`.
"""
from __future__ import annotations

import datetime as dt
import os

from jose import JWTError, jwt

from app.config import settings
from app.core.auth import ALGORITHM
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.integrations.gmail.client import GMAIL_SCOPES

log = get_logger("gmail")

_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_STATE_PURPOSE = "gmail_oauth"
_STATE_TTL_MINUTES = 10

# Google permits http://localhost redirect URIs, but oauthlib refuses insecure
# transport / strict scope unless told otherwise — both are expected in dev.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
if settings.backend_base_url.startswith("http://"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def oauth_client_configured() -> bool:
    """The Connect flow needs an OAuth web client (id + secret)."""
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    return settings.backend_base_url.rstrip("/") + "/integrations/gmail/callback"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [redirect_uri()],
        }
    }


def _build_flow():
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(_client_config(), scopes=GMAIL_SCOPES, redirect_uri=redirect_uri())


def mint_state(admin_id: str) -> str:
    """Short-lived, signed, purpose-scoped state token (not a full identity JWT,
    since it ends up in a URL / browser history / Google logs)."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "purpose": _STATE_PURPOSE,
        "sub": str(admin_id),
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=_STATE_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_state(state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired OAuth state", detail=str(exc)) from exc
    if payload.get("purpose") != _STATE_PURPOSE:
        raise AuthenticationError("Invalid OAuth state")
    return payload


def authorization_url(admin_id: str) -> str:
    flow = _build_flow()
    url, _ = flow.authorization_url(
        access_type="offline",       # request a refresh token
        prompt="consent",            # force a refresh token even on re-consent
        include_granted_scopes="true",
        state=mint_state(admin_id),
    )
    return url


def _fetch_email(creds) -> str | None:
    try:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return svc.users().getProfile(userId="me").execute().get("emailAddress")
    except Exception as exc:
        log.warning("gmail_profile_fetch_failed", error=str(exc))
        return None


def exchange_code(code: str, state: str) -> dict:
    """Validate state, exchange the code, and return token fields (no DB write)."""
    verify_state(state)
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "refresh_token": creds.refresh_token,
        "access_token": creds.token,
        "token_expiry": creds.expiry,
        "email": _fetch_email(creds),
        "scopes": " ".join(creds.scopes) if creds.scopes else None,
    }
