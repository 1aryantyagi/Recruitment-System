"""Interview routes (§8.6)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.feedback_collection import submit_feedback
from app.agents.interview_scheduling import schedule_interview
from app.api.serializers import feedback_dict, interview_dict
from app.core.auth import ensure_can_modify, require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit
from app.core.logging import get_logger
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.models import Candidate, Interview, Requisition, User
from app.models.enums import InterviewStatus, UserRole
from app.schemas.api import FeedbackRequest, ScheduleInterviewRequest, UpdateInterviewRequest
from app.services import flow

router = APIRouter(prefix="/interviews", tags=["interviews"])
log = get_logger("route.interviews")
_HR_DM_ADMIN = require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)


@router.post("")
def create_interview(
    body: ScheduleInterviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    result = schedule_interview(
        candidate_id=body.candidate_id, requisition_id=body.requisition_id,
        interviewer_id=body.interviewer_id, round_type=body.round_type,
        scheduled_at=body.scheduled_at, created_by=str(user.id), meeting_link=body.meeting_link,
    )
    log_audit(db, user_id=user.id, action="SCHEDULED_INTERVIEW", entity_type="interview",
              entity_id=result.get("interview_id"))
    db.commit()
    log.info("route.interviews.scheduled", interview_id=result.get("interview_id"),
             candidate_id=body.candidate_id, requisition_id=body.requisition_id,
             interviewer_id=body.interviewer_id, round_type=body.round_type, created_by=str(user.id))
    interview = db.get(Interview, uuid.UUID(result["interview_id"]))
    return single(interview_dict(interview, with_feedback=True, db=db))


@router.get("")
def list_all_interviews(
    pagination: Pagination = Depends(pagination_params),
    date_from: str | None = Query(default=None, alias="from",
                                  description="ISO date/datetime lower bound on scheduled_at"),
    date_to: str | None = Query(default=None, alias="to",
                                description="ISO date/datetime upper bound on scheduled_at"),
    status: str | None = Query(default=None),
    interviewer_id: str | None = Query(default=None),
    requisition_id: str | None = Query(default=None),
    analyzed: bool | None = Query(default=None, description="Only AI-analyzed interviews"),
    needs_feedback: bool | None = Query(default=None,
                                        description="Completed interviews without submitted human feedback"),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    """Global interview list across all candidates — powers the calendar and the
    evaluations queue. Candidate-scoped history stays at GET /interviews/{candidate_id}."""
    stmt = (
        select(Interview, Candidate.full_name, Requisition.title)
        .join(Candidate, Candidate.id == Interview.candidate_id)
        .join(Requisition, Requisition.id == Interview.requisition_id, isouter=True)
    )
    if date_from:
        stmt = stmt.where(Interview.scheduled_at >= _parse_dt(date_from))
    if date_to:
        stmt = stmt.where(Interview.scheduled_at <= _parse_dt(date_to))
    if status:
        try:
            stmt = stmt.where(Interview.status == InterviewStatus(status))
        except ValueError as exc:
            raise BadRequestError(f"Invalid status: {status}") from exc
    if interviewer_id:
        stmt = stmt.where(Interview.interviewer_id == _uuid(interviewer_id))
    if requisition_id:
        stmt = stmt.where(Interview.requisition_id == _uuid(requisition_id))
    if analyzed is True:
        stmt = stmt.where(Interview.analysis_completed_at.isnot(None))
    if needs_feedback is True:
        stmt = stmt.where(Interview.status == InterviewStatus.COMPLETED)
    stmt = stmt.order_by(Interview.scheduled_at.desc().nullslast(), Interview.created_at.desc())

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).all()
    items = []
    for iv, cand_name, req_title in rows:
        d = interview_dict(iv, with_feedback=True, db=db)
        d["candidate_name"] = cand_name
        d["requisition_title"] = req_title
        items.append(d)
    if needs_feedback is True:
        items = [d for d in items if not (d.get("feedback") or {}).get("is_submitted")]
    log.debug("route.interviews.list_all", total=total, returned=len(items))
    return list_envelope(items, total, pagination.page, pagination.limit)


@router.get("/{candidate_id}")
def list_interviews(
    candidate_id: str,
    pagination: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    stmt = (
        select(Interview).where(Interview.candidate_id == _uuid(candidate_id))
        .order_by(Interview.round_number, Interview.created_at)
    )
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    return list_envelope([interview_dict(i, with_feedback=True, db=db) for i in rows],
                         total, pagination.page, pagination.limit)


@router.patch("/{interview_id}")
def update_interview(
    interview_id: str,
    body: UpdateInterviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    interview = db.get(Interview, _uuid(interview_id))
    if interview is None:
        log.warning("route.interviews.update.not_found", interview_id=interview_id)
        raise NotFoundError("Interview not found")
    ensure_can_modify(user, interview.created_by)
    try:
        interview.status = InterviewStatus(body.status)
    except ValueError as exc:
        raise BadRequestError(f"Invalid status: {body.status}") from exc
    log_audit(db, user_id=user.id, action="UPDATED_INTERVIEW", entity_type="interview", entity_id=interview.id)
    db.commit()
    db.refresh(interview)
    log.info("route.interviews.status_changed", interview_id=str(interview.id),
             new_status=interview.status.value, updated_by=str(user.id))
    return single(interview_dict(interview, with_feedback=True, db=db))


@router.post("/{interview_id}/recording", status_code=status.HTTP_202_ACCEPTED)
def upload_recording(
    interview_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    """Upload an interview recording. Triggers Agent 5 (transcription + AI
    analysis) on the Flow layer; returns 202 immediately (§4.6, §7.5)."""
    interview = db.get(Interview, _uuid(interview_id))
    if interview is None:
        log.warning("route.interviews.recording.not_found", interview_id=interview_id)
        raise NotFoundError("Interview not found")
    ensure_can_modify(user, interview.created_by)
    content = file.file.read()
    log_audit(db, user_id=user.id, action="UPLOADED_RECORDING", entity_type="interview", entity_id=interview.id)
    db.commit()
    background.add_task(flow.run_interview_analysis, str(interview.id), content,
                        file.filename or "interview.mp3", None)
    log.info("route.interviews.recording.dispatch_background", interview_id=str(interview.id),
             uploaded_by=str(user.id))
    return single({"interview_id": str(interview.id), "status": "ACCEPTED",
                   "message": "Recording received; analysis is processing."})


@router.post("/{interview_id}/feedback")
def submit_interview_feedback(
    interview_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    interview = db.get(Interview, _uuid(interview_id))
    if interview is None:
        log.warning("route.interviews.feedback.not_found", interview_id=interview_id)
        raise NotFoundError("Interview not found")
    # The interview's creator or its assigned interviewer may submit feedback.
    ensure_can_modify(user, interview.created_by, interview.interviewer_id)
    fb = submit_feedback(interview_id=interview_id, payload=body.model_dump(exclude_unset=True),
                         submitted_by=str(user.id), db=db)
    log_audit(db, user_id=user.id, action="UPDATED_FEEDBACK", entity_type="interview", entity_id=interview_id)
    db.commit()
    db.refresh(fb)
    log.info("route.interviews.feedback_submitted", interview_id=interview_id, submitted_by=str(user.id))
    return single(feedback_dict(fb))


@router.get("/{interview_id}/feedback")
def get_interview_feedback(
    interview_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    interview = db.get(Interview, _uuid(interview_id))
    if interview is None:
        log.warning("route.interviews.get_feedback.not_found", interview_id=interview_id)
        raise NotFoundError("Interview not found")
    return single({
        "interview": interview_dict(interview, with_feedback=False, db=db),
        "ai_analysis": interview.ai_analysis,
        "ai_overall_rating": interview.ai_overall_rating,
        "feedback": feedback_dict(interview.feedback),
    })


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc


def _parse_dt(value: str) -> dt.datetime:
    """Parse an ISO date or datetime; bare dates become midnight UTC."""
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequestError(f"Invalid date: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed
