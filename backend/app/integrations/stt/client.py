"""Speech-to-text. Prefers Deepgram, falls back to OpenAI Whisper, then to a
clearly-labeled mock transcript when no STT provider is available (§3.5).

Two modes:
  • Batch (``transcribe``): post-call, from a recording URL or raw bytes.
  • Live (``open_live_session``): a streaming WebSocket tap used during a
    Media-Streams call to build the candidate-side transcript in real time.
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

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


# ---------------- live streaming (Media Streams tap) ----------------
OnFinal = Callable[[str], Any] | Callable[[str], Awaitable[None]]


async def open_live_session(on_final: OnFinal, *, language: str | None = None):
    """Open a Deepgram streaming connection for live 8kHz μ-law audio — the format
    Twilio Media Streams sends. ``on_final(text)`` is called for each finalized
    transcript segment (may be sync or async). Feed frames with ``await conn.send(bytes)``
    and end with ``await conn.finish()``. Returns the connection, or ``None`` when
    Deepgram is unavailable / fails to start (caller then degrades gracefully)."""
    if not settings.deepgram_enabled:
        return None
    try:
        from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

        dg = DeepgramClient(settings.deepgram_api_key)
        conn = dg.listen.asyncwebsocket.v("1")

        async def _on_transcript(_client, result, **_kwargs):
            try:
                if not getattr(result, "is_final", False):
                    return
                text = (result.channel.alternatives[0].transcript or "").strip()
                if not text:
                    return
                res = on_final(text)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                log.warning("deepgram_live_transcript_error", error=str(exc))

        async def _on_error(_client, error, **_kwargs):
            log.warning("deepgram_live_error", error=str(error))

        conn.on(LiveTranscriptionEvents.Transcript, _on_transcript)
        conn.on(LiveTranscriptionEvents.Error, _on_error)

        options = LiveOptions(
            model=settings.deepgram_live_model,
            language=language or settings.stt_language or "en",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            interim_results=True,
            punctuate=True,
            smart_format=True,
        )
        if not await conn.start(options):
            log.warning("deepgram_live_start_failed", model=settings.deepgram_live_model)
            return None
        return conn
    except Exception as exc:
        log.warning("deepgram_live_unavailable", error=str(exc))
        return None
