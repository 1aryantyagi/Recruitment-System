"""Flow scheduler — the every-5-minute Gmail poll (§5.6 / §6.2).

Runs inside the Node... err, FastAPI process via APScheduler (no separate
scheduler service), satisfying the single-service constraint. Each polled
attachment runs through the same Agent 1 pipeline as manual uploads; the
gmail_message_id UNIQUE constraint makes ingestion idempotent.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.agents.resume_intake import run_intake
from app.agents.resume_scoring import run_scoring_for_candidate
from app.config import settings
from app.core.logging import get_logger
from app.integrations.gmail import client as gmail
from app.models.enums import CandidateSource

log = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def poll_gmail() -> None:
    if not settings.gmail_enabled:
        return
    messages = gmail.fetch_unread_resumes()
    if not messages:
        return
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
            gmail.mark_read(msg["message_id"])
        except Exception as exc:
            log.warning("gmail_intake_failed", message_id=msg.get("message_id"), error=str(exc))


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
             gmail_enabled=settings.gmail_enabled)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
