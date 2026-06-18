"""Speech-to-text. Prefers Deepgram, falls back to OpenAI Whisper, then to a
clearly-labeled mock transcript when no STT provider is available (§3.5)."""
from __future__ import annotations

from app.config import settings
from app.core.logging import get_logger

log = get_logger("stt")

_MOCK_PREFIX = "[MOCK TRANSCRIPT — no STT provider configured] "


def transcribe(*, audio_url: str | None = None, audio_bytes: bytes | None = None,
               filename: str = "audio.mp3") -> str:
    """Transcribe audio from a URL or raw bytes. Always returns a string."""
    if settings.deepgram_enabled:
        text = _deepgram(audio_url=audio_url, audio_bytes=audio_bytes)
        if text:
            return text
    if settings.openai_api_key and audio_bytes is not None:
        text = _whisper(audio_bytes, filename)
        if text:
            return text
    return _MOCK_PREFIX + (
        "Candidate introduced themselves, described their recent projects, "
        "discussed relevant technical experience, and answered the screening "
        "questions with reasonable clarity."
    )


def _deepgram(*, audio_url: str | None, audio_bytes: bytes | None) -> str | None:
    try:
        from deepgram import DeepgramClient, PrerecordedOptions

        dg = DeepgramClient(settings.deepgram_api_key)
        options = PrerecordedOptions(model="nova-2", smart_format=True, punctuate=True)
        if audio_url:
            resp = dg.listen.rest.v("1").transcribe_url({"url": audio_url}, options)
        elif audio_bytes is not None:
            resp = dg.listen.rest.v("1").transcribe_file({"buffer": audio_bytes}, options)
        else:
            return None
        return resp.results.channels[0].alternatives[0].transcript or None
    except Exception as exc:
        log.warning("deepgram_failed", error=str(exc))
        return None


def _whisper(audio_bytes: bytes, filename: str) -> str | None:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.audio.transcriptions.create(model="whisper-1", file=(filename, audio_bytes))
        return getattr(resp, "text", None)
    except Exception as exc:
        log.warning("whisper_failed", error=str(exc))
        return None
