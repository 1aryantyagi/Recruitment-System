"""Public Twilio webhook routes (§8.5). The only endpoints not requiring HR
auth — every request is verified via the Twilio signature (§12)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.agents.telephonic_screening import next_turn, opening_line
from app.config import settings
from app.core.logging import get_logger, log_step
from app.database.base import SessionLocal
from app.integrations.twilio import client as twilio
from app.models import CallLog, Candidate, Requisition
from app.models.enums import CallStatus
from app.services import flow

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("webhooks")

# Statuses we never downgrade once reached — the conversation already decided the
# call's outcome (completed normally, candidate asked for a callback, or it failed).
_TERMINAL_STATUSES = {CallStatus.COMPLETED, CallStatus.CALLBACK_REQUESTED, CallStatus.FAILED}

_STATUS_MAP = {
    "queued": CallStatus.INITIATED,
    "initiated": CallStatus.INITIATED,
    "ringing": CallStatus.IN_PROGRESS,
    "in-progress": CallStatus.IN_PROGRESS,
    "completed": CallStatus.COMPLETED,
    "busy": CallStatus.FAILED,
    "failed": CallStatus.FAILED,
    "no-answer": CallStatus.NO_ANSWER,
    "canceled": CallStatus.FAILED,
}


async def _verified_form(request: Request) -> dict | None:
    form = dict((await request.form()).items())
    signature = request.headers.get("X-Twilio-Signature")
    url = str(request.url)
    if not twilio.validate_signature(url, form, signature):
        log.warning("twilio_signature_invalid", url=url)
        return None
    return form


def _turn_action_url(next_turn_index: int) -> str:
    return f"{settings.backend_base_url}/webhooks/twilio/turn?turn={next_turn_index}"


@router.post("/twilio/answer")
async def twilio_answer(request: Request):
    """Turn 0 of the screening conversation: introduce the company, confirm who
    we're speaking with, and ask whether now is a good time — then gather the reply."""
    form = await _verified_form(request)
    if form is None:
        return Response(content=twilio.twiml_say_hangup("Unauthorized."), media_type="application/xml", status_code=403)
    sid = form.get("CallSid")
    log.info("webhooks.twilio_answer.received", call_sid=sid)
    opening = opening_line()
    db = SessionLocal()
    streaming_call_id = None
    with log_step(log, "webhooks.twilio_answer", call_sid=sid) as step:
        try:
            call = db.execute(select(CallLog).where(CallLog.twilio_call_sid == sid)).scalar_one_or_none()
            if call is not None:
                step["call_log_id"] = str(call.id)
                if settings.voice_streaming_enabled:
                    # Hand the call to the Media Streams bridge, which builds the greeting
                    # and transcript itself (speech-to-speech). Don't seed the transcript here.
                    streaming_call_id = str(call.id)
                    if call.status == CallStatus.INITIATED:
                        call.status = CallStatus.IN_PROGRESS
                    db.commit()
                    step["mode"] = "streaming"
                else:
                    cand = db.get(Candidate, call.candidate_id)
                    role = ""
                    if call.requisition_id:
                        req = db.get(Requisition, call.requisition_id)
                        role = req.title if req else ""
                    opening = opening_line(candidate_name=cand.full_name if cand else "", role=role)
                    call.transcript = f"Agent: {opening}"
                    if call.status == CallStatus.INITIATED:
                        call.status = CallStatus.IN_PROGRESS
                    db.commit()
                    step["mode"] = "gather"
            else:
                step["call_found"] = False
        finally:
            db.close()
    if streaming_call_id is not None:
        return Response(content=twilio.twiml_stream(streaming_call_id), media_type="application/xml")
    return Response(content=twilio.twiml_gather(opening, _turn_action_url(1)), media_type="application/xml")


def _run_turn(sid: str | None, speech: str, turn: int) -> tuple[str, str]:
    """Blocking work for one conversation turn (DB + the agent's LLM decision).
    Runs in a threadpool so the multi-second LLM call never blocks the event loop.
    Returns ``(action, reply)``."""
    db = SessionLocal()
    try:
        call = db.execute(select(CallLog).where(CallLog.twilio_call_sid == sid)).scalar_one_or_none()
        if call is None:
            return "end_complete", "Goodbye."
        questions = [q.get("question") for q in (call.question_set or [])]
        role = ""
        if call.requisition_id:
            req = db.get(Requisition, call.requisition_id)
            role = req.title if req else ""
        transcript = call.transcript or ""
        if speech:
            transcript = f"{transcript}\nCandidate: {speech}".strip()

        directive = next_turn(questions=questions, transcript=transcript,
                              candidate_speech=speech, turn_index=turn, role=role)
        reply = directive.reply or "Thank you for your time. Goodbye."
        log.info("webhooks.twilio_turn.agent_decision", call_sid=sid, turn=turn,
                 action=directive.action, next_prompt=reply)
        call.transcript = f"{transcript}\nAgent: {reply}".strip()
        if directive.action == "end_unavailable":
            call.status = CallStatus.CALLBACK_REQUESTED
        db.commit()
        return directive.action, reply
    finally:
        db.close()


@router.post("/twilio/turn")
async def twilio_turn(request: Request):
    """Conversation turns (N≥1): capture the candidate's spoken reply, let the
    agent decide the next line, then continue gathering or end the call."""
    form = await _verified_form(request)
    if form is None:
        return Response(content=twilio.twiml_say_hangup("Unauthorized."), media_type="application/xml", status_code=403)
    sid = form.get("CallSid")
    speech = (form.get("SpeechResult") or "").strip()
    try:
        turn = int(request.query_params.get("turn", "1"))
    except (TypeError, ValueError):
        turn = 1
    log.info("webhooks.twilio_turn.received", call_sid=sid, turn=turn, has_speech=bool(speech))

    action, reply = await run_in_threadpool(_run_turn, sid, speech, turn)

    if action == "continue":
        return Response(content=twilio.twiml_gather(reply, _turn_action_url(turn + 1)),
                        media_type="application/xml")
    # end_unavailable / end_complete → speak the closing line and hang up. For a
    # completed screening, the Twilio "completed" status callback drives evaluation.
    return Response(content=twilio.twiml_say_hangup(reply), media_type="application/xml")


@router.post("/twilio")
async def twilio_status(request: Request, background: BackgroundTasks):
    """Twilio status callback. Updates call status; on completion triggers
    transcription + AI evaluation on the Flow layer (idempotent via call SID)."""
    form = await _verified_form(request)
    if form is None:
        return Response(status_code=403)
    sid = form.get("CallSid")
    call_status = (form.get("CallStatus") or "").lower()
    recording_url = form.get("RecordingUrl")
    mapped = _STATUS_MAP.get(call_status)
    log.info("webhooks.twilio_status.received", call_sid=sid, twilio_status=call_status,
             mapped_status=mapped.value if mapped else None, has_recording=bool(recording_url))

    db = SessionLocal()
    call_log_id = None
    final_status = None
    already_done = False
    with log_step(log, "webhooks.twilio_status", call_sid=sid) as step:
        try:
            call = db.execute(select(CallLog).where(CallLog.twilio_call_sid == sid)).scalar_one_or_none()
            if call is None:
                step["call_found"] = False
                return Response(status_code=204)
            # Don't downgrade a call whose conversational outcome is already decided
            # (e.g. the candidate asked for a callback → CALLBACK_REQUESTED).
            if mapped and call.status not in _TERMINAL_STATUSES:
                call.status = mapped
            if recording_url:
                call.recording_url = recording_url
            db.commit()
            call_log_id = str(call.id)
            final_status = call.status
            step["call_log_id"] = call_log_id
            # Post-call evaluation writes screening_answers, so that — not the live
            # transcript — is the "already processed" marker for idempotency.
            already_done = bool(call.screening_answers)
        finally:
            db.close()

    # Process a genuinely completed screening (transcribe + evaluate) asynchronously.
    # Skip callbacks: a candidate who asked to be called back was never screened.
    if (mapped == CallStatus.COMPLETED and call_log_id and not already_done
            and final_status != CallStatus.CALLBACK_REQUESTED):
        background.add_task(flow.run_screening_processing, call_log_id, recording_url)
        log.info("webhooks.twilio_status.dispatch_background", call_log_id=call_log_id,
                 has_recording=bool(recording_url))
    return Response(status_code=204)
