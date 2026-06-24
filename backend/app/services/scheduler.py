"""Flow scheduler — the every-5-minute Gmail poll (§5.6 / §6.2).

Runs inside the Node... err, FastAPI process via APScheduler (no separate
scheduler service), satisfying the single-service constraint. Each polled
attachment runs through the same Agent 1 pipeline as manual uploads; the
gmail_message_id UNIQUE constraint makes ingestion idempotent.
"""
from __future__ import annotations

import datetime as dt
from email.utils import parseaddr

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.agents import feedback_collection as feedback
from app.agents.detail_collection import ingest_detail_reply, request_details
from app.agents.resume_intake import run_intake
from app.agents.resume_scoring import run_scoring_for_candidate
from app.config import settings
from app.core.logging import get_logger, log_step
from app.database.base import SessionLocal
from app.integrations.gmail import client as gmail
from app.integrations.ms_graph import client as graph
from app.models import (
    CandidateDetailRequest,
    DomainTeamsMapping,
    Interview,
    InterviewFeedbackRequest,
)
from app.models.enums import (
    CandidateSource,
    DetailRequestStatus,
    FeedbackRequestStatus,
    InterviewStatus,
)

log = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def poll_gmail() -> None:
    # Broad, DB- and service-account-aware check (not the env-only gmail_enabled).
    if not gmail.gmail_configured():
        log.debug("gmail_poll.skip", reason="not_configured")
        return
    if gmail.is_backed_off():  # auth failed recently; wait out the backoff window
        log.debug("gmail_poll.skip", reason="backed_off")
        return
    with log_step(log, "gmail_poll.cycle") as step:
        messages = gmail.fetch_unread_resumes()
        candidates_created = 0
        scored = 0
        details_requested = 0
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
                        candidates_created += 1
                        try:
                            run_scoring_for_candidate(res["candidate_id"])
                            scored += 1
                        except Exception as exc:
                            log.warning("gmail_scoring_failed", error=str(exc), exc_info=True)
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
                                details_requested += 1
                            except Exception as exc:
                                log.warning("detail_request_failed",
                                            candidate_id=res.get("candidate_id"),
                                            error=str(exc), exc_info=True)
                    gmail.mark_read(msg["message_id"])
                except Exception as exc:
                    log.warning("gmail_intake_failed", message_id=msg.get("message_id"),
                                error=str(exc), exc_info=True)

        step["emails_fetched"] = len(messages)
        step["candidates_created"] = candidates_created
        step["scored"] = scored
        step["details_requested"] = details_requested

        # Always check for replies to outstanding detail requests, even when no new
        # resumes arrived this cycle.
        if settings.detail_collection_enabled:
            step["detail_replies_matched"] = poll_detail_replies()


def poll_detail_replies() -> int:
    """Match unread, attachment-free Gmail replies to outstanding detail requests
    (by thread id), parse them, and write the values onto the candidate.

    Returns the number of replies matched to an outstanding request (for poll-cycle
    metrics)."""
    if not gmail.gmail_configured() or gmail.is_backed_off():
        log.debug("detail_replies_poll.skip")
        return 0
    matched = 0
    with log_step(log, "detail_replies_poll.cycle") as step:
        session = SessionLocal()
        try:
            pending = session.execute(
                select(CandidateDetailRequest).where(
                    CandidateDetailRequest.status == DetailRequestStatus.SENT,
                    CandidateDetailRequest.gmail_thread_id.is_not(None),
                )
            ).scalars().all()
            step["pending"] = len(pending)
            if not pending:
                step["replies_fetched"] = 0
                step["matched"] = 0
                return 0
            by_thread = {r.gmail_thread_id: r for r in pending}
            replies = gmail.fetch_thread_replies(list(by_thread.keys()), db=session)
            step["replies_fetched"] = len(replies)
            for reply in replies:
                req = by_thread.get(reply.get("thread_id"))
                if req is None:
                    continue
                matched += 1
                try:
                    applied = ingest_detail_reply(request=req, reply_text=reply.get("body", ""), db=session)
                    session.commit()
                    gmail.mark_read(reply["message_id"], db=session)
                    log.info("detail_reply_ingested", candidate_id=str(req.candidate_id), applied=applied)
                except Exception as exc:
                    session.rollback()
                    log.warning("detail_reply_failed", message_id=reply.get("message_id"),
                                error=str(exc), exc_info=True)
            step["matched"] = matched
            return matched
        finally:
            session.close()


# ---------------- interview feedback collection (Teams + email) ----------------

def poll_feedback() -> None:
    """Every-N-minute interview feedback cycle: detect concluded interviews and
    request feedback, ingest email replies + Teams channel messages, then send
    reminders / escalate. Each step degrades gracefully and never raises into the
    scheduler loop."""
    if not settings.feedback_collection_enabled:
        log.debug("feedback_poll.skip", reason="disabled")
        return
    with log_step(log, "feedback_poll.cycle") as step:
        step["requested"] = detect_and_request_feedback()
        step["email_matched"] = poll_email_feedback()
        step["teams_matched"] = poll_teams_feedback()
        reminded, escalated = process_feedback_reminders()
        step["reminders_sent"] = reminded
        step["escalations"] = escalated


def detect_and_request_feedback() -> int:
    """SCHEDULED interviews whose scheduled_at + completion buffer has passed and
    that have no feedback request yet → start a feedback cycle. Returns the count."""
    buffer = dt.timedelta(minutes=max(0, settings.interview_completion_buffer_minutes))
    cutoff = dt.datetime.now(dt.timezone.utc) - buffer
    started = 0
    session = SessionLocal()
    try:
        interviews = session.execute(
            select(Interview)
            .outerjoin(InterviewFeedbackRequest,
                       InterviewFeedbackRequest.interview_id == Interview.id)
            .where(
                Interview.status == InterviewStatus.SCHEDULED,
                Interview.scheduled_at.is_not(None),
                Interview.scheduled_at < cutoff,
                InterviewFeedbackRequest.id.is_(None),
            )
        ).scalars().all()
        for interview in interviews:
            try:
                feedback.request_feedback(interview_id=str(interview.id), db=session)
                session.commit()
                started += 1
            except Exception as exc:
                session.rollback()
                log.warning("feedback_request_failed", interview_id=str(interview.id),
                            error=str(exc), exc_info=True)
        return started
    finally:
        session.close()


def poll_email_feedback() -> int:
    """Match unread Gmail replies in feedback-request threads to their requests and
    ingest them. Returns the number of replies recorded as feedback."""
    if not gmail.gmail_configured() or gmail.is_backed_off():
        log.debug("feedback_email_poll.skip")
        return 0
    matched = 0
    session = SessionLocal()
    try:
        pending = session.execute(
            select(InterviewFeedbackRequest).where(
                feedback.monitored_request_condition(),
                InterviewFeedbackRequest.gmail_thread_id.is_not(None),
            )
        ).scalars().all()
        if not pending:
            return 0
        by_thread = {r.gmail_thread_id: r for r in pending}
        replies = gmail.fetch_thread_replies(list(by_thread.keys()), db=session)
        for reply in replies:
            req = by_thread.get(reply.get("thread_id"))
            if req is None:
                continue
            try:
                msg = feedback.ingest_email_feedback(
                    request=req, reply_text=reply.get("body", ""), sender=reply.get("sender"),
                    gmail_message_id=reply.get("message_id"), db=session)
                session.commit()
                gmail.mark_read(reply["message_id"], db=session)
                if msg is not None:
                    matched += 1
            except Exception as exc:
                session.rollback()
                log.warning("feedback_email_failed", message_id=reply.get("message_id"),
                            error=str(exc), exc_info=True)
        return matched
    finally:
        session.close()


def poll_teams_feedback() -> int:
    """Scan each active domain's Teams channel for new feedback messages and ingest
    matches. Returns the number of messages recorded as feedback. No-op when MS
    Graph is in mock mode (creds / ChannelMessage.Read.All permission absent)."""
    if graph.is_mock():
        log.debug("feedback_teams_poll.skip", reason="ms_graph_mock")
        return 0
    matched = 0
    session = SessionLocal()
    try:
        mappings = session.execute(
            select(DomainTeamsMapping).where(DomainTeamsMapping.is_active.is_(True))
        ).scalars().all()
        for mapping in mappings:
            roster = feedback.roster_for_domain(session, mapping.domain_id)
            if not roster:
                continue  # nobody awaiting feedback in this domain — skip the API call
            since_iso = mapping.last_synced_at.isoformat() if mapping.last_synced_at else None
            messages = graph.list_channel_messages(
                mapping.teams_team_id, mapping.teams_channel_id, since_iso=since_iso)
            newest = mapping.last_synced_at
            for message in messages:
                created = graph._parse_iso(message.get("created_at"))
                if created and (newest is None or created > newest):
                    newest = created
                try:
                    msg = feedback.ingest_teams_message(message=message, roster=roster, db=session)
                    session.commit()
                    if msg is not None:
                        matched += 1
                except Exception as exc:
                    session.rollback()
                    log.warning("feedback_teams_failed", message_id=message.get("id"),
                                error=str(exc), exc_info=True)
            # Advance the cursor so the next poll only sees newer messages.
            if newest is not None and newest != mapping.last_synced_at:
                mapping.last_synced_at = newest
                session.commit()
        return matched
    finally:
        session.close()


def process_feedback_reminders() -> tuple[int, int]:
    """Send due reminders (24h / 48h) and escalations (72h) for AWAITING requests.
    Returns (reminders_sent, escalations)."""
    reminded = 0
    escalated = 0
    session = SessionLocal()
    try:
        pending = session.execute(
            select(InterviewFeedbackRequest).where(
                InterviewFeedbackRequest.status == FeedbackRequestStatus.AWAITING,
                InterviewFeedbackRequest.awaiting_since.is_not(None),
            )
        ).scalars().all()
        for req in pending:
            try:
                action = feedback.process_due_reminder(request=req, db=session)
                session.commit()
                if action == "reminder":
                    reminded += 1
                elif action == "escalation":
                    escalated += 1
            except Exception as exc:
                session.rollback()
                log.warning("feedback_reminder_failed", interview_id=str(req.interview_id),
                            error=str(exc), exc_info=True)
        return reminded, escalated
    finally:
        session.close()


def start_scheduler() -> None:
    global _scheduler
    log.info("scheduler.start.begin")
    if _scheduler is not None:
        log.debug("scheduler.start.noop", reason="already_running")
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
    if settings.feedback_collection_enabled:
        _scheduler.add_job(
            poll_feedback,
            "interval",
            minutes=max(1, settings.feedback_poll_interval_minutes),
            id="feedback_poll",
            max_instances=1,
            coalesce=True,
        )
    _scheduler.start()
    log.info("scheduler_started", interval_minutes=settings.gmail_poll_interval_minutes,
             gmail_configured=gmail.gmail_configured(), auth_mode=gmail.current_auth_mode(),
             feedback_collection=settings.feedback_collection_enabled,
             feedback_interval_minutes=settings.feedback_poll_interval_minutes,
             ms_graph_enabled=settings.ms_graph_enabled)


def shutdown_scheduler() -> None:
    global _scheduler
    log.info("scheduler.shutdown.begin")
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler.shutdown.end")
    else:
        log.debug("scheduler.shutdown.noop", reason="not_running")
