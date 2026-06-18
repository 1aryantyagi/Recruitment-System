"""Gmail intake client. Fetches unread emails with PDF/DOCX attachments
(§6.2). No-op (returns []) when Gmail credentials are absent."""
from __future__ import annotations

import base64

from app.config import settings
from app.core.logging import get_logger

log = get_logger("gmail")

_RESUME_EXT = (".pdf", ".docx", ".doc")


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.modify"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def fetch_unread_resumes(max_results: int = 10) -> list[dict]:
    """Return [{message_id, sender, filename, mime_type, content}] for unread
    emails carrying resume attachments. Empty list if Gmail is not configured."""
    if not settings.gmail_enabled:
        return []
    out: list[dict] = []
    try:
        svc = _service()
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
                    "sender": sender,
                    "filename": filename,
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "content": content,
                })
    except Exception as exc:  # graceful degradation
        log.warning("gmail_fetch_failed", error=str(exc))
        return out
    return out


def _iter_parts(payload: dict):
    if not payload:
        return
    yield payload
    for p in payload.get("parts", []) or []:
        yield from _iter_parts(p)


def mark_read(message_id: str) -> None:
    if not settings.gmail_enabled:
        return
    try:
        _service().users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as exc:
        log.warning("gmail_mark_read_failed", error=str(exc), message_id=message_id)
