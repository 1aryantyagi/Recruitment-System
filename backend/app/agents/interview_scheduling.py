"""Agent 4 — Interview Scheduling (synchronous LangGraph, §7.4).

START → validate_no_duplicate_round → create_interview → send_calendar_invite
      → emit_analytics → END
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_event
from app.core.logging import get_logger
from app.database.base import SessionLocal
from app.integrations.ms_graph import client as graph
from app.models import Candidate, Interview, JobApplication, Requisition, User
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


def validate_no_duplicate_round(state: ScheduleState, config) -> dict:
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
    if db.execute(q).first():
        raise BadRequestError(f"A {rtype.value} round is already scheduled for this candidate")
    return {}


def create_interview(state: ScheduleState, config) -> dict:
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
    return {"interview_id": str(interview.id)}


def send_calendar_invite(state: ScheduleState, config) -> dict:
    db = _db(config)
    interview = db.get(Interview, uuid.UUID(state["interview_id"]))
    cand = db.get(Candidate, interview.candidate_id)
    interviewer = db.get(User, interview.interviewer_id) if interview.interviewer_id else None
    req = db.get(Requisition, interview.requisition_id) if interview.requisition_id else None

    start = interview.scheduled_at or dt.datetime.now(dt.timezone.utc)
    end = start + dt.timedelta(hours=1)
    organizer = interviewer.email if interviewer else "scheduler@local.dev"
    attendees = [e for e in [organizer, cand.email if cand and "@placeholder.local" not in cand.email else None] if e]
    subject = f"{interview.round_type.value} Interview — {cand.full_name if cand else 'Candidate'}"
    if req:
        subject += f" ({req.title})"

    meeting = graph.create_meeting(
        organizer_email=organizer, subject=subject,
        start_iso=start.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        end_iso=end.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        attendee_emails=attendees,
    )
    if not interview.meeting_link:
        interview.meeting_link = meeting.get("join_url")
    interview.calendar_event_id = meeting.get("event_id")
    db.flush()
    return {"calendar_event_id": meeting.get("event_id")}


def emit_analytics(state: ScheduleState, config) -> dict:
    db = _db(config)
    interview = db.get(Interview, uuid.UUID(state["interview_id"]))
    log_event(db, EventType.INTERVIEW_SCHEDULED, candidate_id=interview.candidate_id,
              requisition_id=interview.requisition_id, triggered_by=interview.created_by,
              metadata={"round_type": interview.round_type.value})
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
        final = _GRAPH.invoke(state, config={"configurable": {"db": session}})
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
