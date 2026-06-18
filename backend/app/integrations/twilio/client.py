"""Twilio telephonic-screening client (§7.3). Mock mode when Twilio creds are
absent so the screening flow is still fully exercisable in local dev."""
from __future__ import annotations

import re
import uuid
from xml.sax.saxutils import escape

from app.config import settings
from app.core.logging import get_logger

log = get_logger("twilio")

# First-number / separator split: resume extraction can join several numbers
# with commas, slashes, semicolons, newlines, or " or ".
_NUMBER_SEP = re.compile(r"\s*(?:,|/|;|\bor\b|\n)\s*", re.IGNORECASE)


def to_e164(raw: str) -> str:
    """Best-effort E.164 normalization for a stored phone value.

    Resume-extracted phone fields are messy: multiple numbers joined together
    and spaces inside the number, e.g. ``"+91 9058991119, +91 9412447732"``.
    Twilio rejects those (error 21211) — it wants a single number, no spaces,
    ``+`` then digits. We keep the first number and strip all other characters.
    Returns ``""`` (or a bare national number) when no country code is present,
    which the caller treats as invalid rather than guessing a country.
    """
    if not raw:
        return ""
    first = _NUMBER_SEP.split(raw.strip(), maxsplit=1)[0]
    has_plus = first.lstrip().startswith("+")
    digits = re.sub(r"\D", "", first)
    if not digits:
        return ""
    # Keep an explicit '+'; otherwise add one only when a country code looks
    # present (>10 digits). A bare 10-digit national number stays un-prefixed
    # so validation flags it instead of dialing the wrong country.
    if has_plus or len(digits) > 10:
        return "+" + digits
    return digits


def is_mock() -> bool:
    return not settings.twilio_enabled


def start_call(to_number: str, answer_url: str, status_callback: str | None = None) -> dict:
    """Place an outbound screening call. Returns {sid, mock}."""
    if is_mock():
        return {"sid": f"MOCK-{uuid.uuid4().hex[:12]}", "mock": True}
    number = to_e164(to_number)
    if not number.startswith("+") or len(number) < 8:
        log.warning("twilio_invalid_phone", raw=to_number, normalized=number)
        return {"sid": f"MOCK-{uuid.uuid4().hex[:12]}", "mock": True,
                "error": f"invalid phone number: {to_number!r}"}
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(
            to=number,
            from_=settings.twilio_phone_number,
            url=answer_url,
            record=True,
            status_callback=status_callback,
            status_callback_event=["completed"],
        )
        return {"sid": call.sid, "mock": False}
    except Exception as exc:
        log.warning("twilio_call_failed", error=str(exc))
        return {"sid": f"MOCK-{uuid.uuid4().hex[:12]}", "mock": True, "error": str(exc)}


def validate_signature(url: str, params: dict, signature: str | None) -> bool:
    """Verify the Twilio request signature (§12). In mock mode, accept."""
    if is_mock():
        return True
    try:
        from twilio.request_validator import RequestValidator

        return RequestValidator(settings.twilio_auth_token).validate(url, params, signature or "")
    except Exception as exc:
        log.warning("twilio_signature_check_failed", error=str(exc))
        return False


def _say(text: str, voice: str | None = None) -> str:
    """A <Say> using the configured neural voice for a natural-sounding call."""
    v = voice or settings.tts_voice
    voice_attr = f' voice="{escape(v)}"' if v else ""
    return f"<Say{voice_attr}>{escape(text)}</Say>"


def _gather(say_text: str, action_url: str) -> str:
    """A speech <Gather> that speaks a line and waits for the candidate's reply."""
    lang = settings.stt_language
    lang_attr = f' language="{escape(lang)}"' if lang else ""
    return (
        f'<Gather input="speech" action="{escape(action_url)}" method="POST"'
        f' speechTimeout="auto"{lang_attr}>'
        f"{_say(say_text)}"
        "</Gather>"
    )


def twiml_gather(say_text: str, action_url: str) -> str:
    """TwiML for one conversational turn: speak ``say_text`` and gather the spoken
    reply (POSTed to ``action_url``). On silence, re-prompt once, then hang up."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{_gather(say_text, action_url)}"
        f"{_gather('Sorry, I did not catch that. Could you please repeat?', action_url)}"
        f"{_say('No problem, I will have someone reach out to you. Goodbye.')}"
        "<Hangup/>"
        "</Response>"
    )


def twiml_say_hangup(message: str) -> str:
    """TwiML that speaks a closing line (in the configured voice) and hangs up."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{_say(message)}<Hangup/></Response>"
    )
