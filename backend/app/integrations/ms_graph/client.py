"""Microsoft Graph client for interview scheduling (§7.4): free/busy lookup and
Teams online-meeting creation. Mock mode when MS Graph creds are absent.

(The TRD references Google Calendar; this build uses MS Graph to match the
credentials present in `.env` — the scheduling agent treats it as a pluggable
calendar provider.)"""
from __future__ import annotations

import datetime as dt
import re
import uuid

import httpx

from app.config import settings
from app.core.logging import get_logger

log = get_logger("ms_graph")

_GRAPH = "https://graph.microsoft.com/v1.0"

# user_id -> email cache (stable mapping; avoids re-fetching the same author each poll).
_user_email_cache: dict[str, str | None] = {}


def is_mock() -> bool:
    return not settings.ms_graph_enabled


def _app_token() -> str | None:
    log.debug("ms_graph.acquire_token.start")
    try:
        import msal

        app = msal.ConfidentialClientApplication(
            client_id=settings.ms_client_id,
            authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
            client_credential=settings.ms_client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        access_token = result.get("access_token")
        if not access_token:
            log.warning("ms_graph.acquire_token.end", acquired=False,
                        error=result.get("error"))
            return None
        log.debug("ms_graph.acquire_token.end", acquired=True)
        return access_token
    except Exception as exc:
        log.warning("ms_token_failed", error=str(exc), exc_info=True)
        log.warning("ms_graph.acquire_token.error", error=str(exc), exc_info=True)
        return None


def create_meeting(*, organizer_email: str, subject: str, start_iso: str, end_iso: str,
                   attendee_emails: list[str], body: str = "") -> dict:
    """Create a Teams online meeting / calendar event. Returns {event_id, join_url, mock}."""
    log.info("ms_graph.create_meeting.start", organizer=organizer_email,
             attendee_count=len([e for e in attendee_emails if e]),
             start=start_iso, end=end_iso)
    if is_mock():
        log.info("ms_graph.create_meeting.end", mock=True, reason="disabled")
        return _mock_meeting()
    token = _app_token()
    if not token:
        log.warning("ms_graph.create_meeting.end", mock=True, reason="no_token")
        return _mock_meeting()
    try:
        payload = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body or subject},
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": e}, "type": "required"} for e in attendee_emails if e
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }
        resp = httpx.post(
            f"{_GRAPH}/users/{organizer_email}/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        join_url = (data.get("onlineMeeting") or {}).get("joinUrl") or data.get("webLink")
        log.info("ms_graph.create_meeting.end", mock=False, http_status=resp.status_code,
                 event_id=data.get("id"), has_join_url=bool(join_url))
        return {"event_id": data.get("id"), "join_url": join_url, "mock": False}
    except Exception as exc:
        log.warning("ms_create_meeting_failed", error=str(exc), exc_info=True)
        log.warning("ms_graph.create_meeting.error", error=str(exc), mock=True, exc_info=True)
        return _mock_meeting()


def get_availability(emails: list[str], start_iso: str, end_iso: str) -> dict:
    """Return getSchedule results, or {} when unavailable."""
    log.info("ms_graph.get_availability.start", schedule_count=len(emails),
             start=start_iso, end=end_iso)
    if is_mock():
        log.info("ms_graph.get_availability.end", mock=True, reason="disabled")
        return {}
    token = _app_token()
    if not token or not emails:
        log.warning("ms_graph.get_availability.end", mock=True,
                    reason="no_token" if not token else "no_emails")
        return {}
    try:
        resp = httpx.post(
            f"{_GRAPH}/users/{emails[0]}/calendar/getSchedule",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "schedules": emails,
                "startTime": {"dateTime": start_iso, "timeZone": "UTC"},
                "endTime": {"dateTime": end_iso, "timeZone": "UTC"},
                "availabilityViewInterval": 30,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        log.info("ms_graph.get_availability.end", mock=False, http_status=resp.status_code,
                 result_count=len(data.get("value", [])))
        return data
    except Exception as exc:
        log.warning("ms_get_schedule_failed", error=str(exc), exc_info=True)
        log.warning("ms_graph.get_availability.error", error=str(exc), exc_info=True)
        return {}


# ---------------- Teams channel reading (feedback monitoring) ----------------

def _strip_html(html: str) -> str:
    """Crude HTML→text for Teams message bodies (contentType 'html')."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(ent, ch)
    return " ".join(text.split())


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_after(iso: str | None, since_iso: str | None) -> bool:
    """True if `iso` is strictly after `since_iso` (or `since_iso` is unset)."""
    if not since_iso:
        return True
    a, b = _parse_iso(iso), _parse_iso(since_iso)
    if a is None or b is None:
        return True
    return a > b


def _normalize_message(m: dict) -> dict:
    body = m.get("body") or {}
    content = body.get("content") or ""
    text = _strip_html(content) if (body.get("contentType") == "html") else content
    user = (m.get("from") or {}).get("user") or {}
    return {
        "id": m.get("id"),
        "created_at": m.get("createdDateTime"),
        "author_id": user.get("id"),
        "author_name": user.get("displayName"),
        "text": text,
    }


def list_channel_messages(team_id: str, channel_id: str, since_iso: str | None = None,
                          top: int = 50) -> list[dict]:
    """Return normalized channel messages (top-level + replies on active threads)
    newer than `since_iso`, as ``[{id, created_at, author_id, author_name, text}]``.

    Returns [] when MS Graph is in mock mode, unauthorized (e.g. the
    ChannelMessage.Read.All app permission/admin-consent is missing → 403), or on
    any error — graceful degradation, never raises into the poll loop."""
    log.info("ms_graph.list_channel_messages.start", team_id=team_id, channel_id=channel_id,
             since=since_iso, top=top)
    if is_mock():
        log.info("ms_graph.list_channel_messages.end", mock=True, reason="disabled", count=0)
        return []
    token = _app_token()
    if not token or not team_id or not channel_id:
        log.warning("ms_graph.list_channel_messages.end", mock=True, count=0,
                    reason="no_token" if not token else "missing_ids")
        return []
    headers = {"Authorization": f"Bearer {token}"}
    base = f"{_GRAPH}/teams/{team_id}/channels/{channel_id}/messages"
    out: list[dict] = []
    try:
        resp = httpx.get(base, headers=headers, params={"$top": top}, timeout=30)
        resp.raise_for_status()
        for m in resp.json().get("value", []):
            if _is_after(m.get("createdDateTime"), since_iso):
                out.append(_normalize_message(m))
            # Fetch replies only for threads with recent activity (bounds API cost
            # while still catching new replies to older candidate threads).
            if m.get("id") and _is_after(m.get("lastModifiedDateTime") or m.get("createdDateTime"), since_iso):
                try:
                    r = httpx.get(f"{base}/{m['id']}/replies", headers=headers,
                                  params={"$top": 50}, timeout=30)
                    if r.status_code == 200:
                        for rep in r.json().get("value", []):
                            if _is_after(rep.get("createdDateTime"), since_iso):
                                out.append(_normalize_message(rep))
                except Exception as exc:  # one bad thread shouldn't kill the cycle
                    log.debug("ms_graph.list_channel_messages.replies_failed",
                              message_id=m.get("id"), error=str(exc))
        log.info("ms_graph.list_channel_messages.end", mock=False, count=len(out))
        return out
    except Exception as exc:
        log.warning("ms_list_channel_messages_failed", error=str(exc),
                    team_id=team_id, channel_id=channel_id, exc_info=True)
        log.info("ms_graph.list_channel_messages.end", mock=True, count=len(out), error=True)
        return out


def get_user_email(user_id: str | None) -> str | None:
    """Resolve a Teams author's AAD user id to an email (mail / UPN), cached.
    Used to verify a feedback message's author against the assigned interviewer.
    Returns None when unavailable."""
    if not user_id or is_mock():
        return None
    if user_id in _user_email_cache:
        return _user_email_cache[user_id]
    token = _app_token()
    if not token:
        return None
    try:
        resp = httpx.get(f"{_GRAPH}/users/{user_id}", headers={"Authorization": f"Bearer {token}"},
                         params={"$select": "mail,userPrincipalName"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        email = data.get("mail") or data.get("userPrincipalName")
        _user_email_cache[user_id] = email
        return email
    except Exception as exc:
        log.warning("ms_get_user_failed", user_id=user_id, error=str(exc), exc_info=True)
        return None


def list_channels(team_id: str) -> list[dict]:
    """List a team's channels as ``[{id, name}]`` (admin setup helper). [] on error."""
    if is_mock() or not team_id:
        return []
    token = _app_token()
    if not token:
        return []
    try:
        resp = httpx.get(f"{_GRAPH}/teams/{team_id}/channels",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        return [{"id": c.get("id"), "name": c.get("displayName")}
                for c in resp.json().get("value", [])]
    except Exception as exc:
        log.warning("ms_list_channels_failed", team_id=team_id, error=str(exc), exc_info=True)
        return []


def _mock_meeting() -> dict:
    mock_id = f"MOCK-{uuid.uuid4().hex[:12]}"
    return {
        "event_id": mock_id,
        "join_url": f"https://teams.microsoft.com/l/meetup-join/{mock_id}",
        "mock": True,
    }
