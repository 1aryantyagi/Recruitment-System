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
        "have offered to call back. Set qualified=true/false to record your judgement "
        "of the candidate, and scheduled=true only if an interview was booked this call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["complete", "unavailable"]},
            "qualified": {"type": "boolean",
                          "description": "Whether the candidate qualified for an interview round."},
            "scheduled": {"type": "boolean",
                          "description": "Whether an interview slot was booked during this call."},
        },
        "required": ["status"],
    },
}

# Called by the model (when the candidate qualifies) to fetch the interviewer's
# open interview slots. Returns the list as the tool result; the model then reads
# them out and helps the candidate pick one.
GET_SLOTS_TOOL = {
    "type": "function",
    "name": "get_available_slots",
    "description": (
        "Fetch the open interview slots the candidate can book. Call this once you have "
        "judged the candidate qualified and they are willing to schedule. Returns a list "
        "of slots, each with an interviewer_id, a start_iso (UTC), an interviewer_name, and "
        "a human 'label' that already names the interviewer and time (e.g. 'Tue 24 Jun, "
        "4:30 PM with Alice'). Offer ONLY these slots, reading the label so the candidate "
        "hears who they'll meet and when; if the list is empty, tell the candidate someone "
        "will reach out to schedule and end the call."
    ),
    "parameters": {"type": "object", "properties": {}},
}

# Called by the model to book one of the slots returned by get_available_slots.
BOOK_INTERVIEW_TOOL = {
    "type": "function",
    "name": "book_interview",
    "description": (
        "Book a specific interview slot for the candidate. Pass the interviewer_id and "
        "start_iso EXACTLY as given by get_available_slots for the slot the candidate "
        "agreed to. Returns ok=true with a confirmation label, or ok=false with a reason "
        "(e.g. the slot was just taken) — if it fails, offer another open slot."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "interviewer_id": {"type": "string"},
            "start_iso": {"type": "string", "description": "Slot start time in ISO 8601 UTC."},
        },
        "required": ["interviewer_id", "start_iso"],
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
        log.info("openai.realtime.connect.start", model=model)
        # GA Realtime: only the Authorization header — no OpenAI-Beta (that selects
        # the now-disabled preview shape).
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        try:
            ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        except Exception:
            log.error("openai.realtime.connect.error", model=model, exc_info=True)
            raise
        self = cls(ws, model)
        await self._configure(instructions, voice, silence_ms)
        log.info("realtime_connected", model=model)
        log.info("openai.realtime.connect.end", model=model)
        return self

    async def _configure(self, instructions: str, voice: str | None, silence_ms: int | None) -> None:
        # GA nested session schema. Audio is G.711 μ-law ("audio/pcmu") to match
        # Twilio Media Streams with no transcoding.
        resolved_voice = voice or settings.realtime_voice
        resolved_silence_ms = silence_ms or settings.realtime_silence_ms
        log.info(
            "openai.realtime.configure.start",
            model=self._model,
            voice=resolved_voice,
            audio_format="audio/pcmu",
            silence_ms=resolved_silence_ms,
            tools=[t["name"] for t in (END_SCREENING_TOOL, GET_SLOTS_TOOL, BOOK_INTERVIEW_TOOL)],
        )
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
                            "silence_duration_ms": resolved_silence_ms,
                        },
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": resolved_voice,
                    },
                },
                "tools": [END_SCREENING_TOOL, GET_SLOTS_TOOL, BOOK_INTERVIEW_TOOL],
                "tool_choice": "auto",
            },
        })
        log.info("openai.realtime.configure.end", model=self._model)

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
        log.debug("openai.realtime.create_response", has_instructions=bool(instructions))
        await self._send(payload)

    async def cancel_response(self) -> None:
        """Stop the in-progress model response (used on barge-in)."""
        log.debug("openai.realtime.cancel_response")
        await self._send({"type": "response.cancel"})

    async def send_function_result(self, call_id: str, output: dict) -> None:
        """Return a tool's result to the model and prompt it to respond.

        Appends a ``function_call_output`` conversation item for ``call_id`` then
        triggers a new response so the model speaks (reads out slots / confirms a
        booking). Used for the non-terminal tools (get_available_slots, book_interview)."""
        log.debug("openai.realtime.send_function_result", call_id=call_id,
                  output_keys=sorted(output.keys()))
        await self._send({
            "type": "conversation.item.create",
            "item": {"type": "function_call_output", "call_id": call_id,
                     "output": json.dumps(output)},
        })
        await self.create_response()

    async def events(self) -> AsyncIterator[dict]:
        """Yield decoded server events until the socket closes."""
        async for raw in self._ws:
            try:
                yield json.loads(raw)
            except Exception:
                continue

    async def close(self) -> None:
        log.info("openai.realtime.close.start", model=self._model)
        try:
            await self._ws.close()
        except Exception:
            log.debug("openai.realtime.close.error", model=self._model, exc_info=True)
        log.info("openai.realtime.close.end", model=self._model)
