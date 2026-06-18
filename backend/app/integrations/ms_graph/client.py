"""Microsoft Graph client for interview scheduling (§7.4): free/busy lookup and
Teams online-meeting creation. Mock mode when MS Graph creds are absent.

(The TRD references Google Calendar; this build uses MS Graph to match the
credentials present in `.env` — the scheduling agent treats it as a pluggable
calendar provider.)"""
from __future__ import annotations

import uuid

import httpx

from app.config import settings
from app.core.logging import get_logger

log = get_logger("ms_graph")

_GRAPH = "https://graph.microsoft.com/v1.0"


def is_mock() -> bool:
    return not settings.ms_graph_enabled


def _app_token() -> str | None:
    try:
        import msal

        app = msal.ConfidentialClientApplication(
            client_id=settings.ms_client_id,
            authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
            client_credential=settings.ms_client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        return result.get("access_token")
    except Exception as exc:
        log.warning("ms_token_failed", error=str(exc))
        return None


def create_meeting(*, organizer_email: str, subject: str, start_iso: str, end_iso: str,
                   attendee_emails: list[str], body: str = "") -> dict:
    """Create a Teams online meeting / calendar event. Returns {event_id, join_url, mock}."""
    if is_mock():
        return _mock_meeting()
    token = _app_token()
    if not token:
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
        return {"event_id": data.get("id"), "join_url": join_url, "mock": False}
    except Exception as exc:
        log.warning("ms_create_meeting_failed", error=str(exc))
        return _mock_meeting()


def get_availability(emails: list[str], start_iso: str, end_iso: str) -> dict:
    """Return getSchedule results, or {} when unavailable."""
    if is_mock():
        return {}
    token = _app_token()
    if not token or not emails:
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
        return resp.json()
    except Exception as exc:
        log.warning("ms_get_schedule_failed", error=str(exc))
        return {}


def _mock_meeting() -> dict:
    mock_id = f"MOCK-{uuid.uuid4().hex[:12]}"
    return {
        "event_id": mock_id,
        "join_url": f"https://teams.microsoft.com/l/meetup-join/{mock_id}",
        "mock": True,
    }
