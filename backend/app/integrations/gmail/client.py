"""Gmail intake client. Fetches unread emails with PDF/DOCX attachments (§6.2).

Auth is resolved once and cached in-process; short-lived access tokens refresh
automatically. Precedence (highest first):

  1. service_account — Workspace service account impersonating a mailbox (Path A)
  2. oauth_db        — refresh token stored encrypted in the DB (admin Connect flow, Path B)
  3. oauth_env       — legacy static GOOGLE_REFRESH_TOKEN from .env (fallback)

Also sends outbound mail (reply-in-thread) for the candidate detail-collection
flow — `send_reply` works under the existing `gmail.modify` scope, which already
authorizes `users.messages.send` (no extra scope / admin re-consent needed).

No-op (returns [] / does nothing) when Gmail is not configured. On an
unrecoverable auth failure (invalid_grant) the DB credential is disabled, or
env/service-account modes back off exponentially, so polling stops re-logging
the same warning every minute.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import threading
from email.mime.text import MIMEText
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.core.logging import get_logger
from app.database.base import SessionLocal
from app.models.integration import IntegrationCredential

log = get_logger("gmail")

_RESUME_EXT = (".pdf", ".docx", ".doc")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_PROVIDER = "gmail"

# Module-level credential cache + backoff state, guarded by a lock: the
# APScheduler worker thread (polling) and FastAPI request threads (OAuth
# connect/disconnect) both touch them.
_lock = threading.Lock()
_cache: dict = {}    # {"creds": Credentials, "mode": str}
_backoff: dict = {}  # {"until": datetime, "failures": int}  — env / service-account modes only

_BACKOFF_BASE_SECONDS = 60
_BACKOFF_MAX_SECONDS = 3600


# ---------------- time helpers ----------------

def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Coerce a (possibly naive, google sets naive-UTC) datetime to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _naive_utc(value: dt.datetime | None) -> dt.datetime | None:
    """google.oauth2 Credentials expect a naive-UTC `expiry`."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


# ---------------- DB access (mirrors run_intake's optional-session idiom) ----------------

def _load_db_row(db=None) -> IntegrationCredential | None:
    own = db is None
    session = db or SessionLocal()
    try:
        return session.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        # Table not migrated yet, or DB unreachable: treat as "no DB credential"
        # so auth falls back to env / service account instead of crashing the poll.
        if own:
            session.rollback()
        log.debug("gmail_db_unavailable", error=str(exc))
        return None
    finally:
        if own:
            session.close()


def _mark_disabled(error: str, db=None) -> None:
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
        if row is not None:
            row.disabled = True
            row.last_error = (error or "")[:1000]
            if own:
                session.commit()
    except Exception as exc:
        if own:
            session.rollback()
        log.warning("gmail_mark_disabled_failed", error=str(exc), exc_info=True)
    finally:
        if own:
            session.close()


def _persist_refreshed(creds, db=None) -> None:
    """Write the freshly-minted access token (and rotated refresh token, if any)
    back to the DB row so a restart reuses them. oauth_db mode only."""
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
        if row is None:
            return
        row.access_token = creds.token
        row.token_expiry = _aware_utc(getattr(creds, "expiry", None))
        new_refresh = getattr(creds, "refresh_token", None)
        if new_refresh and new_refresh != row.refresh_token:
            row.refresh_token = new_refresh
            log.info("gmail_refresh_token_rotated", auth_mode="oauth_db")
        row.last_synced_at = _utcnow()
        row.last_error = None
        if own:
            session.commit()
    except Exception as exc:
        if own:
            session.rollback()
        log.warning("gmail_persist_failed", error=str(exc), exc_info=True)
    finally:
        if own:
            session.close()


# ---------------- credential resolution + caching ----------------

def _load_service_account_info() -> dict:
    raw = settings.google_service_account_json.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    return json.loads(Path(raw).read_text(encoding="utf-8"))


def _resolve_credentials(db=None):
    """Return (credentials, auth_mode) by precedence, or (None, None) if unconfigured."""
    # 1. Service account (Path A) — highest precedence.
    if settings.gmail_service_account_enabled:
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(
            _load_service_account_info(), scopes=GMAIL_SCOPES
        ).with_subject(settings.gmail_impersonate_email)
        return creds, "service_account"

    # 2. DB-stored OAuth token (Path B).
    row = _load_db_row(db)
    if row is not None and not row.disabled and row.refresh_token:
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            # Only trust a cached access token when we also know its expiry;
            # otherwise force a refresh so we never use a silently-stale token.
            token=row.access_token if row.token_expiry else None,
            refresh_token=row.refresh_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            token_uri=_TOKEN_URI,
            scopes=GMAIL_SCOPES,
            expiry=_naive_utc(row.token_expiry),
        )
        return creds, "oauth_db"

    # 3. Legacy .env refresh token (fallback).
    if settings.gmail_enabled:
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            token_uri=_TOKEN_URI,
            scopes=GMAIL_SCOPES,
        )
        return creds, "oauth_env"

    return None, None


def _enter_backoff(mode: str, error: str) -> None:
    with _lock:
        failures = _backoff.get("failures", 0) + 1
        delay = min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** (failures - 1)))
        _backoff["failures"] = failures
        _backoff["until"] = _utcnow() + dt.timedelta(seconds=delay)
    # Logged once per backoff window (not every poll), so no 60s spam.
    log.warning(
        "gmail_auth_failed",
        auth_mode=mode,
        impersonated=settings.gmail_impersonate_email or None,
        error=error,
        backoff_seconds=delay,
        failures=failures,
    )


def _handle_refresh_error(mode: str, error: str, db=None) -> None:
    with _lock:
        _cache.clear()  # force a clean rebuild on the next attempt
    if mode == "oauth_db":
        _mark_disabled(error, db=db)
        # gmail_configured() now excludes this row, so polling self-silences
        # until an admin reconnects (which clears the cache + disabled flag).
        log.warning("gmail_auth_revoked", auth_mode=mode, error=error,
                    action="reconnect_required")
        return
    _enter_backoff(mode, error)  # service_account / oauth_env have no DB row


def _ensure_credentials(db=None):
    """Resolve + cache credentials and refresh the access token when expired.
    Returns valid credentials or None (unconfigured / backed off / auth failed)."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request

    if is_backed_off():
        return None

    with _lock:
        creds = _cache.get("creds")
        mode = _cache.get("mode")
    if creds is None:
        creds, mode = _resolve_credentials(db)
        if creds is None:
            return None
        with _lock:
            _cache["creds"], _cache["mode"] = creds, mode

    if not creds.valid:
        log.debug("gmail.refresh_token.start", auth_mode=mode)
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            _handle_refresh_error(mode, str(exc), db=db)
            return None
        except Exception as exc:  # transient network/etc — don't disable, just skip this poll
            log.warning("gmail_refresh_failed", auth_mode=mode, error=str(exc), exc_info=True)
            return None
        with _lock:
            _backoff.clear()  # any success resets the backoff window
        log.debug("gmail.refresh_token.end", auth_mode=mode)
        if mode == "oauth_db":
            _persist_refreshed(creds, db=db)
    return creds


def _service(db=None):
    """Return an authorized Gmail API service, or None when unavailable."""
    from googleapiclient.discovery import build

    creds = _ensure_credentials(db)
    if creds is None:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------------- public state helpers ----------------

def is_backed_off() -> bool:
    with _lock:
        until = _backoff.get("until")
    return until is not None and _utcnow() < until


def gmail_configured(db=None) -> bool:
    """True when any auth path can serve Gmail. Used by the scheduler in place of
    the env-only settings.gmail_enabled."""
    if settings.gmail_service_account_enabled:
        return True
    row = _load_db_row(db)
    if row is not None and not row.disabled and row.refresh_token:
        return True
    return settings.gmail_enabled


def clear_cache() -> None:
    """Drop cached credentials + backoff so a reconnect/disconnect takes effect now."""
    with _lock:
        _cache.clear()
        _backoff.clear()


def current_auth_mode(db=None) -> str:
    if settings.gmail_service_account_enabled:
        return "service_account"
    row = _load_db_row(db)
    if row is not None and not row.disabled and row.refresh_token:
        return "oauth_db"
    if settings.gmail_enabled:
        return "oauth_env"
    return "none"


def get_status(db=None) -> dict:
    """Connection status for the admin endpoint — never includes token values."""
    row = _load_db_row(db)
    mode = current_auth_mode(db)
    if mode == "service_account":
        connected_email = settings.gmail_impersonate_email
    elif mode == "oauth_db" and row is not None:
        connected_email = row.connected_email
    else:
        connected_email = None
    return {
        "configured": mode != "none",
        "connected": mode != "none",
        "auth_mode": mode,
        "connected_email": connected_email,
        "disabled": bool(row.disabled) if row is not None else False,
        "last_error": row.last_error if row is not None else None,
        "last_synced_at": row.last_synced_at.isoformat() if row is not None and row.last_synced_at else None,
        "poll_interval_minutes": max(1, settings.gmail_poll_interval_minutes),
        "backed_off": is_backed_off(),
    }


# ---------------- OAuth Connect-flow persistence (Path B) ----------------

def upsert_oauth_credentials(*, refresh_token: str | None, access_token: str | None = None,
                             token_expiry: dt.datetime | None = None,
                             connected_email: str | None = None,
                             scopes: str | None = None, db=None) -> bool:
    """Store tokens from the admin Connect flow (encrypted). Google omits the
    refresh token on repeat consent — in that case the existing one is kept.
    Returns True if the row ends up with a usable refresh token."""
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
        if row is None:
            row = IntegrationCredential(provider=_PROVIDER)
            session.add(row)
        if refresh_token:
            row.refresh_token = refresh_token
        if access_token is not None:
            row.access_token = access_token
        row.token_expiry = _aware_utc(token_expiry)
        if connected_email:
            row.connected_email = connected_email
        if scopes:
            row.scopes = scopes
        row.auth_mode = "oauth_db"
        row.disabled = False
        row.last_error = None
        row.last_synced_at = _utcnow()
        has_token = bool(row.refresh_token)
        if own:
            session.commit()
        return has_token
    finally:
        if own:
            session.close()
        clear_cache()


def disconnect(db=None) -> None:
    """Clear stored OAuth tokens (admin disconnect). Does not affect env / SA modes."""
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
        if row is not None:
            row.refresh_token = None
            row.access_token = None
            row.token_expiry = None
            row.disabled = False
            row.last_error = None
            row.auth_mode = None
            row.connected_email = None
            if own:
                session.commit()
    finally:
        if own:
            session.close()
        clear_cache()


# ---------------- intake (unchanged contract) ----------------

def fetch_unread_resumes(max_results: int = 10, db=None) -> list[dict]:
    """Return [{message_id, sender, filename, mime_type, content}] for unread
    emails carrying resume attachments. Empty list if Gmail is not configured."""
    log.info("gmail.fetch.start", max_results=max_results, auth_mode=current_auth_mode(db))
    if not gmail_configured(db):
        log.info("gmail.fetch.end", configured=False, count=0)
        return []
    out: list[dict] = []
    try:
        svc = _service(db)
        if svc is None:
            log.info("gmail.fetch.end", service=False, count=0)
            return out
        listing = (
            svc.users().messages()
            .list(userId="me", q="is:unread has:attachment", maxResults=max_results)
            .execute()
        )
        for ref in listing.get("messages", []):
            msg = svc.users().messages().get(userId="me", id=ref["id"]).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            sender = headers.get("from", "")
            for part in _iter_parts(msg.get("payload", {})):
                filename = part.get("filename") or ""
                if not filename.lower().endswith(_RESUME_EXT):
                    continue
                body = part.get("body", {})
                att_id = body.get("attachmentId")
                if not att_id:
                    continue
                att = (
                    svc.users().messages().attachments()
                    .get(userId="me", messageId=ref["id"], id=att_id).execute()
                )
                content = base64.urlsafe_b64decode(att["data"])
                out.append({
                    "message_id": ref["id"],
                    "thread_id": msg.get("threadId"),
                    "sender": sender,
                    "subject": headers.get("subject", ""),
                    "message_id_header": headers.get("message-id"),  # RFC822 id, for In-Reply-To
                    "filename": filename,
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "content": content,
                })
    except Exception as exc:  # graceful degradation
        log.warning("gmail_fetch_failed", error=str(exc), exc_info=True)
        log.info("gmail.fetch.end", count=len(out), error=True)
        return out
    log.info("gmail.fetch.end", count=len(out))
    return out


def _iter_parts(payload: dict):
    if not payload:
        return
    yield payload
    for p in payload.get("parts", []) or []:
        yield from _iter_parts(p)


def _extract_plain_text(payload: dict) -> str:
    """Best-effort plain-text body from a Gmail message payload (for reply parsing)."""
    for part in _iter_parts(payload):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                try:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    continue
    return ""


def mark_read(message_id: str, db=None) -> None:
    log.info("gmail.mark_read.start", message_id=message_id)
    if not gmail_configured(db):
        log.info("gmail.mark_read.end", configured=False, message_id=message_id)
        return
    try:
        svc = _service(db)
        if svc is None:
            log.info("gmail.mark_read.end", service=False, message_id=message_id)
            return
        svc.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        log.info("gmail.mark_read.end", message_id=message_id)
    except Exception as exc:
        log.warning("gmail_mark_read_failed", error=str(exc), message_id=message_id, exc_info=True)


# ---------------- outbound + reply intake (detail-collection flow) ----------------

def send_reply(*, to: str, subject: str, body: str, thread_id: str | None = None,
               in_reply_to: str | None = None, db=None) -> str | None:
    """Send a plain-text email, optionally threaded as a reply (`thread_id` keeps
    it in the same Gmail conversation; `in_reply_to` is the original RFC822
    Message-ID, set as In-Reply-To/References so the candidate's client threads it).

    Returns the sent message id, or None when Gmail is unavailable or the send
    fails — graceful degradation, never raises into the poll loop. Works under the
    existing `gmail.modify` scope."""
    log.info("gmail.send.start", to=to, threaded=bool(thread_id))
    if not gmail_configured(db):
        log.info("gmail.send.end", configured=False, to=to)
        return None
    try:
        svc = _service(db)
        if svc is None:
            log.info("gmail.send.end", service=False, to=to)
            return None
        mime = MIMEText(body or "", "plain", "utf-8")
        mime["To"] = to
        mime["Subject"] = subject
        if in_reply_to:
            mime["In-Reply-To"] = in_reply_to
            mime["References"] = in_reply_to
        send_body: dict = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")}
        if thread_id:
            send_body["threadId"] = thread_id
        sent = svc.users().messages().send(userId="me", body=send_body).execute()
        message_id = sent.get("id")
        log.info("gmail.send.end", to=to, message_id=message_id)
        return message_id
    except Exception as exc:
        log.warning("gmail_send_failed", error=str(exc), to=to, exc_info=True)
        log.info("gmail.send.end", to=to, error=True)
        return None


def send_email(*, to: str, subject: str, body: str, db=None) -> dict | None:
    """Send a plain-text email on a NEW thread and return
    ``{"message_id", "thread_id"}`` (Gmail's send response carries the threadId).

    Used to start a trackable thread (e.g. an interviewer feedback request) whose
    reply is later matched back by `thread_id` via `fetch_thread_replies`. Returns
    None when Gmail is unavailable or the send fails — graceful degradation, never
    raises into the poll loop. Works under the existing `gmail.modify` scope."""
    log.info("gmail.send_email.start", to=to)
    if not gmail_configured(db):
        log.info("gmail.send_email.end", configured=False, to=to)
        return None
    try:
        svc = _service(db)
        if svc is None:
            log.info("gmail.send_email.end", service=False, to=to)
            return None
        mime = MIMEText(body or "", "plain", "utf-8")
        mime["To"] = to
        mime["Subject"] = subject
        send_body = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")}
        sent = svc.users().messages().send(userId="me", body=send_body).execute()
        result = {"message_id": sent.get("id"), "thread_id": sent.get("threadId")}
        log.info("gmail.send_email.end", to=to, message_id=result["message_id"],
                 thread_id=result["thread_id"])
        return result
    except Exception as exc:
        log.warning("gmail_send_email_failed", error=str(exc), to=to, exc_info=True)
        log.info("gmail.send_email.end", to=to, error=True)
        return None


def fetch_thread_replies(thread_ids, max_results: int = 20, db=None) -> list[dict]:
    """Return [{message_id, thread_id, sender, body}] for unread, attachment-free
    messages whose Gmail thread is in `thread_ids` — i.e. candidate replies to a
    detail-request email. Excludes attachments so it never collides with the
    resume poller. Empty list if Gmail is unconfigured or nothing matches."""
    wanted = {t for t in (thread_ids or []) if t}
    log.info("gmail.fetch_replies.start", thread_count=len(wanted), max_results=max_results)
    if not wanted or not gmail_configured(db):
        log.info("gmail.fetch_replies.end", count=0,
                 reason="no_threads" if not wanted else "not_configured")
        return []
    out: list[dict] = []
    try:
        svc = _service(db)
        if svc is None:
            return out
        listing = (
            svc.users().messages()
            .list(userId="me", q="is:unread -has:attachment", maxResults=max_results)
            .execute()
        )
        for ref in listing.get("messages", []):
            msg = svc.users().messages().get(userId="me", id=ref["id"]).execute()
            thread_id = msg.get("threadId")
            if thread_id not in wanted:
                continue
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            out.append({
                "message_id": ref["id"],
                "thread_id": thread_id,
                "sender": headers.get("from", ""),
                "body": _extract_plain_text(msg.get("payload", {})),
            })
    except Exception as exc:  # graceful degradation
        log.warning("gmail_fetch_replies_failed", error=str(exc), exc_info=True)
        log.info("gmail.fetch_replies.end", count=len(out), error=True)
        return out
    log.info("gmail.fetch_replies.end", count=len(out))
    return out
