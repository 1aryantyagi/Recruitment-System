"""Agent 6 — Feedback Collection (§7.6).

Auto-chained after Agent 5: notifies the interviewer (email/in-app) with a link
to the feedback form. Notify is a small LangGraph:
  START → resolve_interviewer → send_notification → emit_analytics → END

The human feedback submission itself (`POST /interviews/{id}/feedback`) is a
separate action handled by `submit_feedback`, which upserts interview_feedback.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.core.errors import NotFoundError
from app.core.events import log_event
from app.core.logging import get_logger, log_step
from app.database.base import SessionLocal
from app.models import Interview, InterviewFeedback, User
from app.models.enums import EventType, Recommendation

log = get_logger("agent.feedback")


class NotifyState(TypedDict, total=False):
    interview_id: str
    interviewer_email: str | None
    form_link: str


def _db(config) -> Any:
    return config["configurable"]["db"]


def resolve_interviewer(state: NotifyState, config) -> dict:
    with log_step(log, "agent.feedback.resolve_interviewer", interview_id=state.get("interview_id")) as step:
        db = _db(config)
        interview = db.get(Interview, uuid.UUID(state["interview_id"]))
        if interview is None:
            raise NotFoundError("Interview not found")
        interviewer = db.get(User, interview.interviewer_id) if interview.interviewer_id else None
        link = f"{settings.frontend_base_url}/interviews/{interview.candidate_id}?interview={interview.id}"
        # Ensure a feedback record exists (draft) for the interviewer to complete.
        if interview.feedback is None:
            db.add(InterviewFeedback(interview_id=interview.id, is_submitted=False))
            db.flush()
            log.debug("agent.feedback.draft_created", interview_id=state.get("interview_id"))
        step["has_interviewer"] = interviewer is not None
        return {"interviewer_email": interviewer.email if interviewer else None, "form_link": link}


def send_notification(state: NotifyState, config) -> dict:
    with log_step(log, "agent.feedback.send_notification", interview_id=state.get("interview_id")):
        # No email provider is configured in local dev — log the in-app notification.
        log.info(
            "feedback_notification",
            interview_id=state["interview_id"],
            to=state.get("interviewer_email") or "(unassigned)",
            form_link=state.get("form_link"),
        )
        return {}


def emit_analytics(state: NotifyState, config) -> dict:
    with log_step(log, "agent.feedback.emit_analytics", interview_id=state.get("interview_id")):
        db = _db(config)
        interview = db.get(Interview, uuid.UUID(state["interview_id"]))
        log_event(db, "FEEDBACK_REQUESTED", candidate_id=interview.candidate_id,
                  requisition_id=interview.requisition_id, metadata={"interview_id": state["interview_id"]})
        return {}


def build_notify_graph():
    g = StateGraph(NotifyState)
    g.add_node("resolve_interviewer", resolve_interviewer)
    g.add_node("send_notification", send_notification)
    g.add_node("emit_analytics", emit_analytics)
    g.add_edge(START, "resolve_interviewer")
    g.add_edge("resolve_interviewer", "send_notification")
    g.add_edge("send_notification", "emit_analytics")
    g.add_edge("emit_analytics", END)
    return g.compile()


_GRAPH = build_notify_graph()


def notify_for_interview(*, interview_id: str, db=None) -> dict:
    own = db is None
    session = db or SessionLocal()
    try:
        with log_step(log, "agent.feedback.notify", interview_id=str(interview_id)):
            final = _GRAPH.invoke({"interview_id": str(interview_id)}, config={"configurable": {"db": session}})
        if own:
            session.commit()
        return {"interview_id": str(interview_id), "form_link": final.get("form_link")}
    except Exception:
        if own:
            session.rollback()
        raise
    finally:
        if own:
            session.close()


def submit_feedback(*, interview_id: str, payload: dict, submitted_by: str | None, db) -> InterviewFeedback:
    """Upsert human feedback for an interview (callable multiple times — §7.6)."""
    with log_step(
        log,
        "agent.feedback.submit_feedback",
        interview_id=str(interview_id),
        submitted_by=submitted_by,
    ) as step:
        interview = db.get(Interview, uuid.UUID(str(interview_id)))
        if interview is None:
            raise NotFoundError("Interview not found")
        fb = interview.feedback
        if fb is None:
            fb = InterviewFeedback(interview_id=interview.id)
            db.add(fb)

        now = dt.datetime.now(dt.timezone.utc)
        for field in ("human_summary", "human_strengths", "human_concerns", "technical_rating",
                      "communication_rating", "problem_solving_rating", "culture_fit_rating", "overall_rating"):
            if field in payload and payload[field] is not None:
                setattr(fb, field, payload[field])
        if payload.get("recommendation"):
            try:
                fb.recommendation = Recommendation(payload["recommendation"])
            except ValueError:
                pass
        fb.submitted_by = uuid.UUID(submitted_by) if submitted_by else fb.submitted_by
        is_submitted = payload.get("is_submitted", True)
        if is_submitted and not fb.is_submitted:
            fb.submitted_at = now
        fb.is_submitted = bool(is_submitted)
        fb.last_updated_at = now
        db.flush()

        if fb.is_submitted:
            log_event(db, EventType.FEEDBACK_SUBMITTED, candidate_id=interview.candidate_id,
                      requisition_id=interview.requisition_id,
                      triggered_by=uuid.UUID(submitted_by) if submitted_by else None,
                      metadata={"interview_id": str(interview.id), "recommendation": payload.get("recommendation")})
        step["is_submitted"] = bool(is_submitted)
        step["recommendation"] = payload.get("recommendation")
        return fb
