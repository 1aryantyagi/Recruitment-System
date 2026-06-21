"""Twilio telephonic-screening client (§7.3). Mock mode when Twilio creds are
absent so the screening flow is still fully exercisable in local dev."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
import uuid
from xml.sax.saxutils import escape, quoteattr

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


# ---------------- Media Streams (low-latency speech-to-speech) ----------------
# A Twilio Media Streams WebSocket isn't signature-verified the way HTTP webhooks
# are, so we mint a short-lived HMAC token (over the call_log_id) into the stream
# URL <Parameter> and verify it on the `start` event in the WS bridge.
_TOKEN_TTL_SECONDS = 3600


def sign_stream_token(call_log_id: str) -> str:
    """Signed, expiring token binding a media-stream WS to a specific call."""
    exp = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{call_log_id}:{exp}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def verify_stream_token(token: str, call_log_id: str) -> bool:
    """Validate a token minted by :func:`sign_stream_token` for ``call_log_id``."""
    try:
        padded = token + "=" * (-len(token) % 4)
        cid, exp_s, sig = base64.urlsafe_b64decode(padded.encode()).decode().rsplit(":", 2)
        if cid != call_log_id or int(exp_s) < int(time.time()):
            return False
        expected = hmac.new(settings.secret_key.encode(), f"{cid}:{exp_s}".encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


def twiml_stream(call_log_id: str, ws_url: str | None = None) -> str:
    """TwiML that bridges the call's audio to our media-stream WebSocket
    (``<Connect><Stream>``), passing the call id and a signed token as custom
    parameters. Twilio holds the call open until the WebSocket disconnects."""
    url = ws_url or f"{settings.public_ws_base_url}/webhooks/twilio/media-stream"
    token = sign_stream_token(call_log_id)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f"<Stream url={quoteattr(url)}>"
        f'<Parameter name="call_log_id" value={quoteattr(call_log_id)}/>'
        f'<Parameter name="token" value={quoteattr(token)}/>'
        "</Stream>"
        "</Connect>"
        "</Response>"
    )


def hangup_call(call_sid: str) -> bool:
    """End an in-progress call via the REST API (used when the agent decides the
    screening is complete from inside the media-stream bridge). No-op in mock mode."""
    if is_mock() or not call_sid:
        return False
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.calls(call_sid).update(twiml="<Response><Hangup/></Response>")
        return True
    except Exception as exc:
        log.warning("twilio_hangup_failed", error=str(exc), call_sid=call_sid)
        return False
