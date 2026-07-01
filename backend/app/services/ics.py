"""Minimal RFC 5545 iCalendar (.ics) builder for interview invites.

Produces a single-VEVENT VCALENDAR with ``METHOD:REQUEST`` so mail clients
(Gmail / Outlook / Apple Mail) render it as an invitation with RSVP buttons. Kept
pure (no I/O) so it is unit-testable offline; the Gmail client attaches the
returned string as a ``text/calendar`` part (and a downloadable ``invite.ics``).
"""
from __future__ import annotations

import datetime as dt


def _fmt_utc(value: dt.datetime) -> str:
    """A UTC timestamp in iCalendar form: ``YYYYMMDDTHHMMSSZ``."""
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11 (\\ ; , and newlines)."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold a long content line to <=75 chars with CRLF + a leading space
    (RFC 5545 §3.1). Folds on character boundaries; invite fields are short and
    overwhelmingly ASCII, so this stays well within the octet limit in practice."""
    if len(line) <= 75:
        return line
    parts = [line[:75]]
    rest = line[75:]
    while rest:
        parts.append(" " + rest[:74])  # leading space marks a continuation
        rest = rest[74:]
    return "\r\n".join(parts)


def build_invite_ics(
    *,
    uid: str,
    summary: str,
    start_utc: dt.datetime,
    end_utc: dt.datetime,
    organizer_email: str,
    organizer_name: str = "",
    attendees: list[dict] | None = None,
    description: str = "",
    location: str = "",
    method: str = "REQUEST",
    sequence: int = 0,
    now: dt.datetime | None = None,
) -> str:
    """Build an .ics invitation string.

    ``attendees`` is a list of ``{"email": str, "name": str}``; entries without an
    email are skipped. ``now`` overrides DTSTAMP (for deterministic tests)."""
    stamp = now or dt.datetime.now(dt.timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Talent OS//Interview Scheduler//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(stamp)}",
        f"DTSTART:{_fmt_utc(start_utc)}",
        f"DTEND:{_fmt_utc(end_utc)}",
        f"SEQUENCE:{sequence}",
        "STATUS:CONFIRMED",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    org_cn = f";CN={_escape(organizer_name)}" if organizer_name else ""
    lines.append(f"ORGANIZER{org_cn}:mailto:{organizer_email}")
    for a in attendees or []:
        email = (a or {}).get("email")
        if not email:
            continue
        cn = f";CN={_escape(a.get('name', ''))}" if a.get("name") else ""
        lines.append(
            f"ATTENDEE{cn};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:"
            f"mailto:{email}"
        )
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
