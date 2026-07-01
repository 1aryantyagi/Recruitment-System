"""Agent 4 — Interview Scheduling (synchronous LangGraph, §7.4).

START → validate_no_duplicate_round → create_interview → send_calendar_invite
      → emit_analytics → END
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.config import settings
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_event
from app.core.logging import get_logger, log_step
from app.database.base import SessionLocal
from app.integrations.gmail import client as gmail
from app.models import Candidate, Interview, JobApplication, Requisition, User
from app.services.ics import build_invite_ics
from app.models.enums import ApplicationStatus, EventType, InterviewStatus, RoundType
from app.models.logs import ApplicationStatusHistory

log = get_logger("agent.scheduling")

_ROUND_NUMBER = {RoundType.L1: 1, RoundType.L2: 2, RoundType.L3: 3}


class ScheduleState(TypedDict, total=False):
    candidate_id: str
    requisition_id: str | None
    interviewer_id: str | None
    round_type: str
    scheduled_at: str  # ISO 8601
    meeting_link: str | None
    created_by: str | None
    interview_id: str
    calendar_event_id: str | None


def _db(config) -> Any:
    return config["configurable"]["db"]


# Assumed interview length when checking whether an interviewer is double-booked.
_INTERVIEW_MINUTES = 60


def validate_no_duplicate_round(state: ScheduleState, config) -> dict:
    with log_step(log, "scheduling.validate_no_duplicate_round",
                  candidate_id=state.get("candidate_id"),
                  requisition_id=state.get("requisition_id"),
                  interviewer_id=state.get("interviewer_id"),
                  round_type=state.get("round_type")) as step:
        db = _db(config)
        cid = uuid.UUID(state["candidate_id"])
        rtype = RoundType(state["round_type"])
        q = select(Interview.id).where(
            Interview.candidate_id == cid,
            Interview.round_type == rtype,
            Interview.status.in_([InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED]),
        )
        if state.get("requisition_id"):
            q = q.where(Interview.requisition_id == uuid.UUID(state["requisition_id"]))
        duplicate = db.execute(q).first() is not None
        step["duplicate_round_found"] = duplicate
        log.debug("scheduling.validate_no_duplicate_round.duplicate_check",
                  round_type=rtype.value, duplicate_found=duplicate)
        if duplicate:
            log.warning("scheduling.validate_no_duplicate_round.duplicate_round",
                        candidate_id=str(cid), round_type=rtype.value)
            raise BadRequestError(f"A {rtype.value} round is already scheduled for this candidate")

        # Don't double-book the interviewer: reject if they already have an active
        # round overlapping this time (assuming ~1h interviews).
        interviewer_id = state.get("interviewer_id")
        scheduled_at = _parse_dt(state.get("scheduled_at"))
        if interviewer_id and scheduled_at:
            window = dt.timedelta(minutes=_INTERVIEW_MINUTES)
            clash = db.execute(
                select(Interview.id).where(
                    Interview.interviewer_id == uuid.UUID(interviewer_id),
                    Interview.status.in_([InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED]),
                    Interview.scheduled_at.is_not(None),
                    Interview.scheduled_at > scheduled_at - window,
                    Interview.scheduled_at < scheduled_at + window,
                )
            ).first()
            interviewer_clash = clash is not None
            step["interviewer_clash_found"] = interviewer_clash
            log.debug("scheduling.validate_no_duplicate_round.interviewer_availability",
                      interviewer_id=interviewer_id, window_minutes=_INTERVIEW_MINUTES,
                      clash_found=interviewer_clash)
            if interviewer_clash:
                log.warning("scheduling.validate_no_duplicate_round.interviewer_double_booked",
                            interviewer_id=interviewer_id)
                raise BadRequestError("The interviewer already has an interview at that time")
        else:
            log.debug("scheduling.validate_no_duplicate_round.interviewer_check_skipped",
                      has_interviewer=bool(interviewer_id), has_scheduled_at=bool(scheduled_at))
        return {}


def create_interview(state: ScheduleState, config) -> dict:
    with log_step(log, "scheduling.create_interview",
                  candidate_id=state.get("candidate_id"),
                  requisition_id=state.get("requisition_id"),
                  round_type=state.get("round_type")) as step:
        db = _db(config)
        rtype = RoundType(state["round_type"])
        scheduled_at = _parse_dt(state.get("scheduled_at"))
        interview = Interview(
            candidate_id=uuid.UUID(state["candidate_id"]),
            requisition_id=uuid.UUID(state["requisition_id"]) if state.get("requisition_id") else None,
            interviewer_id=uuid.UUID(state["interviewer_id"]) if state.get("interviewer_id") else None,
            round_number=_ROUND_NUMBER.get(rtype, 1),
            round_type=rtype,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            meeting_link=state.get("meeting_link"),
            created_by=uuid.UUID(state["created_by"]) if state.get("created_by") else None,
        )
        db.add(interview)
        db.flush()
        step["interview_id"] = str(interview.id)
        step["round_number"] = _ROUND_NUMBER.get(rtype, 1)
        log.debug("scheduling.create_interview.flushed", interview_id=str(interview.id),
                  scheduled_at=scheduled_at.isoformat() if scheduled_at else None)
        return {"interview_id": str(interview.id)}


def _company_tz() -> ZoneInfo:
    """Company-local zone for the human-readable date/time in the invite body."""
    try:
        return ZoneInfo(settings.company_timezone)
    except Exception:
        return ZoneInfo("UTC")


# Seed / synthetic domains that are not real deliverable mailboxes.
_PLACEHOLDER_DOMAINS = {"local.dev", "placeholder.local", "example.com"}


def _real_email(email: str | None) -> bool:
    """True for a deliverable external address — excludes seed/placeholder domains
    (e.g. the demo interviewers' ``@local.dev``), so we never email a fake mailbox."""
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].lower() not in _PLACEHOLDER_DOMAINS


def send_calendar_invite(state: ScheduleState, config) -> dict:
    """Email the candidate an .ics interview invite via Gmail. Records whether the
    invite actually went out on ``interview.invite_sent`` and logs an error (rather
    than faking success) when it didn't — the booking itself is never rolled back."""
    with log_step(log, "scheduling.send_calendar_invite",
                  interview_id=state.get("interview_id")) as step:
        db = _db(config)
        interview = db.get(Interview, uuid.UUID(state["interview_id"]))
        cand = db.get(Candidate, interview.candidate_id)
        interviewer = db.get(User, interview.interviewer_id) if interview.interviewer_id else None
        req = db.get(Requisition, interview.requisition_id) if interview.requisition_id else None
        log.debug("scheduling.send_calendar_invite.context",
                  interview_id=str(interview.id),
                  has_candidate=cand is not None, has_interviewer=interviewer is not None,
                  has_requisition=req is not None)

        start = interview.scheduled_at or dt.datetime.now(dt.timezone.utc)
        end = start + dt.timedelta(hours=1)
        round_label = interview.round_type.value
        role = req.title if req else None
        cand_email = cand.email if cand and _real_email(cand.email) else None
        # cc the interviewer only when they have a real (deliverable) mailbox.
        cc = [interviewer.email] if interviewer and _real_email(interviewer.email) else []

        subject = f"{round_label} Interview — {cand.full_name if cand else 'Candidate'}"
        if role:
            subject += f" ({role})"

        sent = None
        if cand_email:
            tz = _company_tz()
            when_local = (
                start.astimezone(tz).strftime("%A, %d %b %Y at %I:%M %p").replace(" 0", " ")
            )
            link = interview.meeting_link
            first = cand.full_name.split(" ")[0] if cand and cand.full_name else "there"
            body_lines = [
                f"Hi {first},",
                "",
                f"Your {round_label} interview{f' for {role}' if role else ''} is scheduled for:",
                f"    {when_local} ({settings.company_timezone})",
            ]
            if interviewer and interviewer.name:
                body_lines.append(f"    Interviewer: {interviewer.name}")
            if link:
                body_lines.append(f"    Join link: {link}")
            body_lines += [
                "",
                "A calendar invite is attached — add it to your calendar to confirm.",
                "We look forward to speaking with you.",
                "",
                f"— {settings.company_name} Talent Team",
            ]
            body = "\n".join(body_lines)
            description = f"{round_label} interview" + (f" for {role}" if role else "")
            if link:
                description += f"\nJoin link: {link}"

            organizer = gmail.account_email(db) or "no-reply@talent-os.local"
            attendees = [{"email": cand_email, "name": cand.full_name if cand else ""}]
            if interviewer and _real_email(interviewer.email):
                attendees.append({"email": interviewer.email, "name": interviewer.name or ""})
            ics = build_invite_ics(
                uid=f"{interview.id}@talent-os",
                summary=subject,
                start_utc=start,
                end_utc=end,
                organizer_email=organizer,
                organizer_name=settings.company_name,
                attendees=attendees,
                description=description,
                location=link or "",
            )
            with log_step(log, "scheduling.send_calendar_invite.gmail_send",
                          to=cand_email, cc_count=len(cc),
                          configured=gmail.gmail_configured(db)) as call_step:
                sent = gmail.send_invite(to=cand_email, subject=subject, body=body,
                                         ics=ics, cc=cc, db=db)
                call_step["sent"] = bool(sent)

        if sent:
            interview.invite_sent = True
            interview.calendar_event_id = f"gmail:{sent.get('message_id')}"
            step["invite_sent"] = True
            step["calendar_event_id"] = interview.calendar_event_id
            log.info("scheduling.send_calendar_invite.sent", interview_id=str(interview.id),
                     to=cand_email, message_id=sent.get("message_id"))
        else:
            interview.invite_sent = False
            reason = (
                "no_candidate_email" if not cand_email
                else "gmail_not_configured" if not gmail.gmail_configured(db)
                else "send_failed"
            )
            step["invite_sent"] = False
            step["failure_reason"] = reason
            # Surface loudly: the interview is booked but the candidate was NOT emailed.
            log.error("scheduling.send_calendar_invite.failed", interview_id=str(interview.id),
                      candidate_id=str(interview.candidate_id), to=cand_email, reason=reason)
        db.flush()
        return {"calendar_event_id": interview.calendar_event_id}


def emit_analytics(state: ScheduleState, config) -> dict:
    with log_step(log, "scheduling.emit_analytics",
                  interview_id=state.get("interview_id")) as step:
        db = _db(config)
        interview = db.get(Interview, uuid.UUID(state["interview_id"]))
        log_event(db, EventType.INTERVIEW_SCHEDULED, candidate_id=interview.candidate_id,
                  requisition_id=interview.requisition_id, triggered_by=interview.created_by,
                  metadata={"round_type": interview.round_type.value})
        log.debug("scheduling.emit_analytics.event_emitted",
                  event_type=EventType.INTERVIEW_SCHEDULED.value,
                  candidate_id=str(interview.candidate_id),
                  round_type=interview.round_type.value)
        # Advance the application into the interview stage.
        if interview.requisition_id:
            app = db.execute(select(JobApplication).filter_by(
                candidate_id=interview.candidate_id, requisition_id=interview.requisition_id)).scalar_one_or_none()
            if app and app.status != ApplicationStatus.INTERVIEW_SCHEDULED:
                prev = app.status
                app.status = ApplicationStatus.INTERVIEW_SCHEDULED
                db.add(ApplicationStatusHistory(application_id=app.id, from_status=prev,
                                                to_status=ApplicationStatus.INTERVIEW_SCHEDULED,
                                                reason_note=f"{interview.round_type.value} scheduled"))
                step["application_status_advanced"] = True
                log.info("scheduling.emit_analytics.application_advanced",
                         application_id=str(app.id),
                         from_status=prev.value if prev else None,
                         to_status=ApplicationStatus.INTERVIEW_SCHEDULED.value)
            else:
                step["application_status_advanced"] = False
                log.debug("scheduling.emit_analytics.application_advance_skipped",
                          has_application=app is not None,
                          already_scheduled=bool(app and app.status == ApplicationStatus.INTERVIEW_SCHEDULED))
        return {}


def _parse_dt(value) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        log.debug("scheduling.parse_dt.failed", value=str(value))
        return None


def build_scheduling_graph():
    g = StateGraph(ScheduleState)
    g.add_node("validate", validate_no_duplicate_round)
    g.add_node("create_interview", create_interview)
    g.add_node("send_invite", send_calendar_invite)
    g.add_node("emit_analytics", emit_analytics)
    g.add_edge(START, "validate")
    g.add_edge("validate", "create_interview")
    g.add_edge("create_interview", "send_invite")
    g.add_edge("send_invite", "emit_analytics")
    g.add_edge("emit_analytics", END)
    return g.compile()


_GRAPH = build_scheduling_graph()


def schedule_interview(*, candidate_id, requisition_id, interviewer_id, round_type,
                       scheduled_at, created_by=None, meeting_link=None, db=None) -> dict:
    own = db is None
    session = db or SessionLocal()
    state: ScheduleState = {
        "candidate_id": str(candidate_id),
        "requisition_id": str(requisition_id) if requisition_id else None,
        "interviewer_id": str(interviewer_id) if interviewer_id else None,
        "round_type": round_type.value if isinstance(round_type, RoundType) else str(round_type),
        "scheduled_at": scheduled_at if isinstance(scheduled_at, str) else (scheduled_at.isoformat() if scheduled_at else None),
        "meeting_link": meeting_link,
        "created_by": str(created_by) if created_by else None,
    }
    try:
        with log_step(log, "scheduling.schedule_interview",
                      candidate_id=str(candidate_id),
                      requisition_id=str(requisition_id) if requisition_id else None,
                      interviewer_id=str(interviewer_id) if interviewer_id else None,
                      round_type=state["round_type"],
                      owns_session=own) as step:
            final = _GRAPH.invoke(state, config={"configurable": {"db": session}})
            step["interview_id"] = final.get("interview_id")
            step["calendar_event_id"] = final.get("calendar_event_id")
        if own:
            session.commit()
        return {"interview_id": final.get("interview_id"),
                "calendar_event_id": final.get("calendar_event_id")}
    except Exception:
        if own:
            session.rollback()
        raise
    finally:
        if own:
            session.close()
