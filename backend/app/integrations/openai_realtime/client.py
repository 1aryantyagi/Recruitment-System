"""OpenAI Realtime API client — a thin async wrapper over the Realtime WebSocket
used to run the live screening conversation (speech-to-speech).

Targets the **GA** Realtime API: a ``gpt-realtime`` family model, no ``OpenAI-Beta``
header, and the nested ``session.audio.{input,output}`` schema. (The older
``*-realtime-preview`` flat schema with ``OpenAI-Beta: realtime=v1`` has been
disabled server-side — it now fails with ``beta_api_shape_disabled``.)

Audio in/out is ``audio/pcmu`` (8kHz G.711 μ-law) to match Twilio Media Streams
exactly, so audio passes through both directions with no transcoding.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import websockets

from app.config import settings
from app.core.logging import get_logger

log = get_logger("openai.realtime")

_REALTIME_URL = "wss://api.openai.com/v1/realtime"

# Single function tool: the model calls this (after a spoken goodbye) to end the
# call. Replaces the legacy ConversationDirective.action field.
END_SCREENING_TOOL = {
    "type": "function",
    "name": "end_screening",
    "description": (
        "End the screening call. Call this ONLY after you have spoken a brief, warm "
        "goodbye line. Use status='complete' once all screening questions have been "
        "covered; use status='unavailable' if the candidate cannot talk now and you "
        "have offered to call back."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["complete", "unavailable"]},
        },
        "required": ["status"],
    },
}


class RealtimeSession:
    """An open Realtime WebSocket. Use :meth:`connect` to create one."""

    def __init__(self, ws: "websockets.ClientConnection", model: str) -> None:
        self._ws = ws
        self._model = model

    @classmethod
    async def connect(cls, *, instructions: str, voice: str | None = None,
                      silence_ms: int | None = None, model: str | None = None) -> "RealtimeSession":
        """Open the WS, configure the session, and return the session handle.

        Raises on connection failure so the caller can fall back to the IVR path."""
        model = model or settings.openai_realtime_model
        url = f"{_REALTIME_URL}?model={model}"
        # GA Realtime: only the Authorization header — no OpenAI-Beta (that selects
        # the now-disabled preview shape).
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        self = cls(ws, model)
        await self._configure(instructions, voice, silence_ms)
        log.info("realtime_connected", model=model)
        return self

    async def _configure(self, instructions: str, voice: str | None, silence_ms: int | None) -> None:
        # GA nested session schema. Audio is G.711 μ-law ("audio/pcmu") to match
        # Twilio Media Streams with no transcoding.
        await self._send({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self._model,
                "output_modalities": ["audio"],
                "instructions": instructions,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcmu"},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": silence_ms or settings.realtime_silence_ms,
                        },
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": voice or settings.realtime_voice,
                    },
                },
                "tools": [END_SCREENING_TOOL],
                "tool_choice": "auto",
            },
        })

    async def _send(self, obj: dict) -> None:
        await self._ws.send(json.dumps(obj))

    async def send_audio(self, b64_ulaw: str) -> None:
        """Append a base64-encoded μ-law audio chunk to the input buffer.
        With server_vad, OpenAI commits + responds automatically on end-of-speech."""
        await self._send({"type": "input_audio_buffer.append", "audio": b64_ulaw})

    async def create_response(self, instructions: str | None = None) -> None:
        """Ask the model to generate a response now (used to make the agent greet
        first, before the candidate has said anything)."""
        payload: dict = {"type": "response.create"}
        if instructions:
            payload["response"] = {"instructions": instructions}
        await self._send(payload)

    async def cancel_response(self) -> None:
        """Stop the in-progress model response (used on barge-in)."""
        await self._send({"type": "response.cancel"})

    async def events(self) -> AsyncIterator[dict]:
        """Yield decoded server events until the socket closes."""
        async for raw in self._ws:
            try:
                yield json.loads(raw)
            except Exception:
                continue

    async def close(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass
