"""Flow scheduler — the every-5-minute Gmail poll (§5.6 / §6.2).

Runs inside the Node... err, FastAPI process via APScheduler (no separate
scheduler service), satisfying the single-service constraint. Each polled
attachment runs through the same Agent 1 pipeline as manual uploads; the
gmail_message_id UNIQUE constraint makes ingestion idempotent.
"""
from __future__ import annotations

from email.utils import parseaddr

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.agents.detail_collection import ingest_detail_reply, request_details
from app.agents.resume_intake import run_intake
from app.agents.resume_scoring import run_scoring_for_candidate
from app.config import settings
from app.core.logging import get_logger
from app.database.base import SessionLocal
from app.integrations.gmail import client as gmail
from app.models import CandidateDetailRequest
from app.models.enums import CandidateSource, DetailRequestStatus

log = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def poll_gmail() -> None:
    # Broad, DB- and service-account-aware check (not the env-only gmail_enabled).
    if not gmail.gmail_configured():
        return
    if gmail.is_backed_off():  # auth failed recently; wait out the backoff window
        return
    messages = gmail.fetch_unread_resumes()
    if messages:
        log.info("gmail_poll", found=len(messages))
        for msg in messages:
            try:
                res = run_intake(
                    file_content=msg["content"],
                    file_name=msg["filename"],
                    mime_type=msg["mime_type"],
                    source=CandidateSource.GMAIL,
                    source_detail=msg.get("sender"),
                    gmail_message_id=msg["message_id"],
                )
                if res.get("candidate_id") and not res.get("skipped"):
                    try:
                        run_scoring_for_candidate(res["candidate_id"])
                    except Exception as exc:
                        log.warning("gmail_scoring_failed", error=str(exc))
                    # Ask the new applicant for the logistics fields the resume omitted.
                    if settings.detail_collection_enabled:
                        try:
                            request_details(
                                candidate_id=res["candidate_id"],
                                to_email=parseaddr(msg.get("sender") or "")[1],
                                thread_id=msg.get("thread_id"),
                                original_message_id=msg.get("message_id_header"),
                                subject=msg.get("subject"),
                            )
                        except Exception as exc:
                            log.warning("detail_request_failed",
                                        candidate_id=res.get("candidate_id"), error=str(exc))
                gmail.mark_read(msg["message_id"])
            except Exception as exc:
                log.warning("gmail_intake_failed", message_id=msg.get("message_id"), error=str(exc))

    # Always check for replies to outstanding detail requests, even when no new
    # resumes arrived this cycle.
    if settings.detail_collection_enabled:
        poll_detail_replies()


def poll_detail_replies() -> None:
    """Match unread, attachment-free Gmail replies to outstanding detail requests
    (by thread id), parse them, and write the values onto the candidate."""
    if not gmail.gmail_configured() or gmail.is_backed_off():
        return
    session = SessionLocal()
    try:
        pending = session.execute(
            select(CandidateDetailRequest).where(
                CandidateDetailRequest.status == DetailRequestStatus.SENT,
                CandidateDetailRequest.gmail_thread_id.is_not(None),
            )
        ).scalars().all()
        if not pending:
            return
        by_thread = {r.gmail_thread_id: r for r in pending}
        replies = gmail.fetch_thread_replies(list(by_thread.keys()), db=session)
        for reply in replies:
            req = by_thread.get(reply.get("thread_id"))
            if req is None:
                continue
            try:
                applied = ingest_detail_reply(request=req, reply_text=reply.get("body", ""), db=session)
                session.commit()
                gmail.mark_read(reply["message_id"], db=session)
                log.info("detail_reply_ingested", candidate_id=str(req.candidate_id), applied=applied)
            except Exception as exc:
                session.rollback()
                log.warning("detail_reply_failed", message_id=reply.get("message_id"), error=str(exc))
    finally:
        session.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        poll_gmail,
        "interval",
        minutes=max(1, settings.gmail_poll_interval_minutes),
        id="gmail_poll",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("scheduler_started", interval_minutes=settings.gmail_poll_interval_minutes,
             gmail_configured=gmail.gmail_configured(), auth_mode=gmail.current_auth_mode())


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
