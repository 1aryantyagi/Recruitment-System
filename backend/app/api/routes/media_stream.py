"""Twilio Media Streams ↔ OpenAI Realtime bridge — the low-latency (speech-to-
speech) screening path. Enabled when ``settings.voice_streaming_enabled``.

Flow per call:
  Twilio  ──(8kHz μ-law over WS)──▶  this bridge  ──▶  OpenAI Realtime (audio→audio)
                                          └──────────▶  Deepgram live (transcript tap)
  OpenAI audio deltas  ──(μ-law)──▶  Twilio (no transcoding — both are g711_ulaw)

The candidate-side transcript comes from Deepgram, the agent side from Realtime
``audio_transcript`` events; both are assembled into ``CallLog.transcript`` so the
existing post-call evaluation graph (which prefers that field) runs unchanged. The
call ends when the model calls the ``end_screening`` tool → we hang up via REST,
which fires Twilio's "completed" status callback → post-call processing as today.
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.agents.telephonic_screening import realtime_instructions
from app.core.logging import get_logger
from app.database.base import SessionLocal
from app.integrations.openai_realtime.client import RealtimeSession
from app.integrations.stt import client as stt
from app.integrations.twilio import client as twilio
from app.models import CallLog, Candidate, Requisition
from app.models.enums import CallStatus

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("media_stream")

# Twilio mark name used to detect when the agent's goodbye has finished playing
# before we hang up (so the closing line isn't cut off).
_END_MARK = "end-of-call"
# Safety cap on how long to wait for that mark echo before hanging up anyway.
_HANGUP_MAX_WAIT = 12.0
# Statuses we never downgrade (mirrors webhooks._TERMINAL_STATUSES).
_TERMINAL = {CallStatus.COMPLETED, CallStatus.CALLBACK_REQUESTED, CallStatus.FAILED}


# ---------------- blocking DB helpers (run in threadpool) ----------------
def _load_context(call_log_id: str) -> dict | None:
    db = SessionLocal()
    try:
        call = db.get(CallLog, uuid.UUID(call_log_id))
        if call is None:
            return None
        questions = [q.get("question") for q in (call.question_set or [])]
        role = ""
        if call.requisition_id:
            req = db.get(Requisition, call.requisition_id)
            role = req.title if req else ""
        cand = db.get(Candidate, call.candidate_id)
        cand_name = cand.full_name if cand else ""
        if call.status == CallStatus.INITIATED:
            call.status = CallStatus.IN_PROGRESS
            db.commit()
        return {"questions": questions, "role": role, "candidate_name": cand_name}
    finally:
        db.close()


def _save_transcript(call_log_id: str, transcript: str, status: CallStatus | None = None) -> None:
    db = SessionLocal()
    try:
        call = db.get(CallLog, uuid.UUID(call_log_id))
        if call is None:
            return
        if transcript:
            call.transcript = transcript
        if status is not None and call.status not in _TERMINAL:
            call.status = status
        db.commit()
    finally:
        db.close()


class _Transcript:
    """Thread-safe, incrementally-persisted conversation transcript."""

    def __init__(self, call_log_id: str) -> None:
        self.call_log_id = call_log_id
        self._lines: list[str] = []
        self._lock = asyncio.Lock()

    def text(self) -> str:
        return "\n".join(self._lines)

    async def add(self, speaker: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        async with self._lock:
            self._lines.append(f"{speaker}: {text}")
            snapshot = "\n".join(self._lines)
        await run_in_threadpool(_save_transcript, self.call_log_id, snapshot, None)

    async def set_status(self, status: CallStatus) -> None:
        await run_in_threadpool(_save_transcript, self.call_log_id, self.text(), status)


# ---------------- the bridge ----------------
@router.websocket("/twilio/media-stream")
async def media_stream(ws: WebSocket) -> None:
    await ws.accept()
    realtime: RealtimeSession | None = None
    dg = None
    transcript: _Transcript | None = None
    try:
        # 1) Handshake: read until Twilio's "start" event; verify the signed token.
        stream_sid = call_sid = call_log_id = None
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("event") != "start":
                continue  # ignore "connected" and anything before "start"
            start = msg.get("start", {})
            stream_sid = start.get("streamSid") or msg.get("streamSid")
            call_sid = start.get("callSid")
            params = start.get("customParameters") or {}
            call_log_id = params.get("call_log_id")
            token = params.get("token") or ""
            break
        if not call_log_id or not twilio.verify_stream_token(token, call_log_id):
            log.warning("media_stream_unauthorized", call_log_id=call_log_id)
            await ws.close(code=4403)
            return

        ctx = await run_in_threadpool(_load_context, call_log_id)
        if ctx is None:
            log.warning("media_stream_call_not_found", call_log_id=call_log_id)
            await ws.close()
            return
        transcript = _Transcript(call_log_id)

        # 2) Connect OpenAI Realtime (instructions reuse opening_line + next_turn rules).
        instructions = realtime_instructions(
            questions=ctx["questions"], role=ctx["role"], candidate_name=ctx["candidate_name"])
        try:
            realtime = await RealtimeSession.connect(instructions=instructions)
        except Exception as exc:
            log.warning("realtime_connect_failed", error=str(exc), call_log_id=call_log_id)
            if call_sid:
                await run_in_threadpool(twilio.hangup_call, call_sid)  # avoid dead air
            await ws.close()
            return

        # 3) Deepgram transcript tap on the candidate's audio (best-effort).
        async def _on_candidate_final(text: str) -> None:
            await transcript.add("Candidate", text)

        dg = await stt.open_live_session(_on_candidate_final)

        # 4) Agent greets first.
        await realtime.create_response()

        # 5) Pump both directions; stop as soon as either side ends.
        bridge = _Bridge(ws, realtime, transcript, dg, stream_sid, call_sid)
        ai_task = asyncio.create_task(bridge.run_ai_to_twilio())
        tw_task = asyncio.create_task(bridge.run_twilio_to_ai())
        done, pending = await asyncio.wait({ai_task, tw_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("media_stream_error", error=str(exc))
    finally:
        if dg is not None:
            try:
                await dg.finish()
            except Exception:
                pass
        if realtime is not None:
            await realtime.close()
        if transcript is not None:
            await run_in_threadpool(_save_transcript, transcript.call_log_id, transcript.text())


class _Bridge:
    """Pumps audio both ways between Twilio and OpenAI Realtime, tracking response
    state for clean barge-in and using a Twilio mark to hang up only after the
    agent's goodbye has actually played out."""

    def __init__(self, ws: WebSocket, realtime: RealtimeSession, transcript: _Transcript,
                 dg, stream_sid: str | None, call_sid: str | None) -> None:
        self.ws = ws
        self.realtime = realtime
        self.transcript = transcript
        self.dg = dg
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.response_active = False           # is the model currently speaking?
        self._ending = False                   # end_screening already handled?
        self._final_mark = asyncio.Event()     # set when Twilio echoes _END_MARK

    async def _to_twilio(self, obj: dict) -> None:
        await self.ws.send_text(json.dumps(obj))

    async def run_twilio_to_ai(self) -> None:
        """Forward inbound caller audio to OpenAI (and the Deepgram tap)."""
        try:
            while True:
                msg = json.loads(await self.ws.receive_text())
                event = msg.get("event")
                if event == "media":
                    payload = msg.get("media", {}).get("payload")
                    if not payload:
                        continue
                    await self.realtime.send_audio(payload)  # base64 μ-law, passthrough
                    if self.dg is not None:
                        try:
                            await self.dg.send(base64.b64decode(payload))
                        except Exception:
                            pass
                elif event == "mark":
                    if msg.get("mark", {}).get("name") == _END_MARK:
                        self._final_mark.set()
                elif event == "stop":
                    return
        except WebSocketDisconnect:
            return

    async def run_ai_to_twilio(self) -> None:
        """Forward model audio to Twilio, handle barge-in, capture the agent
        transcript, and end the call when the model calls ``end_screening``."""
        async for event in self.realtime.events():
            etype = event.get("type", "")

            # Agent audio out → Twilio (μ-law passthrough).
            if etype in ("response.audio.delta", "response.output_audio.delta"):
                delta = event.get("delta")
                if delta and self.stream_sid:
                    await self._to_twilio({
                        "event": "media", "streamSid": self.stream_sid,
                        "media": {"payload": delta},
                    })

            elif etype == "response.created":
                self.response_active = True
            elif etype == "response.done":
                self.response_active = False

            # Candidate started talking → flush queued agent audio + cancel, but only
            # if the agent is actually mid-response (else OpenAI errors "no active response").
            elif etype == "input_audio_buffer.speech_started":
                if self.response_active:
                    if self.stream_sid:
                        await self._to_twilio({"event": "clear", "streamSid": self.stream_sid})
                    await self.realtime.cancel_response()
                    self.response_active = False

            # Agent's spoken text → transcript.
            elif etype in ("response.audio_transcript.done", "response.output_audio_transcript.done"):
                await self.transcript.add("Agent", event.get("transcript", ""))

            # The model decided to end the call (it has already spoken a goodbye).
            elif (etype == "response.function_call_arguments.done"
                  and event.get("name") == "end_screening" and not self._ending):
                self._ending = True
                status = "complete"
                try:
                    status = json.loads(event.get("arguments") or "{}").get("status") or "complete"
                except Exception:
                    pass
                if status == "unavailable":
                    await self.transcript.set_status(CallStatus.CALLBACK_REQUESTED)
                # Hang up after the goodbye finishes; keep forwarding any trailing
                # audio meanwhile (the drain runs as its own task).
                if self.stream_sid:
                    await self._to_twilio({
                        "event": "mark", "streamSid": self.stream_sid,
                        "mark": {"name": _END_MARK},
                    })
                asyncio.create_task(self._drain_and_hangup())

            elif etype == "error":
                log.warning("realtime_event_error", detail=str(event.get("error")))

    async def _drain_and_hangup(self) -> None:
        try:
            await asyncio.wait_for(self._final_mark.wait(), timeout=_HANGUP_MAX_WAIT)
        except asyncio.TimeoutError:
            pass
        if self.call_sid:
            await run_in_threadpool(twilio.hangup_call, self.call_sid)
