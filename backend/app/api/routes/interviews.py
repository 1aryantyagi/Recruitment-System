"""Interview routes (§8.6)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.feedback_collection import submit_feedback
from app.agents.interview_scheduling import schedule_interview
from app.api.serializers import feedback_dict, interview_dict
from app.core.auth import require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.models import Interview, User
from app.models.enums import InterviewStatus, UserRole
from app.schemas.api import FeedbackRequest, ScheduleInterviewRequest, UpdateInterviewRequest
from app.services import flow

router = APIRouter(prefix="/interviews", tags=["interviews"])
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
    interview = db.get(Interview, uuid.UUID(result["interview_id"]))
    return single(interview_dict(interview, with_feedback=True, db=db))


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
        raise NotFoundError("Interview not found")
    try:
        interview.status = InterviewStatus(body.status)
    except ValueError as exc:
        raise BadRequestError(f"Invalid status: {body.status}") from exc
    log_audit(db, user_id=user.id, action="UPDATED_INTERVIEW", entity_type="interview", entity_id=interview.id)
    db.commit()
    db.refresh(interview)
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
        raise NotFoundError("Interview not found")
    content = file.file.read()
    log_audit(db, user_id=user.id, action="UPLOADED_RECORDING", entity_type="interview", entity_id=interview.id)
    db.commit()
    background.add_task(flow.run_interview_analysis, str(interview.id), content,
                        file.filename or "interview.mp3", None)
    return single({"interview_id": str(interview.id), "status": "ACCEPTED",
                   "message": "Recording received; analysis is processing."})


@router.post("/{interview_id}/feedback")
def submit_interview_feedback(
    interview_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    fb = submit_feedback(interview_id=interview_id, payload=body.model_dump(exclude_unset=True),
                         submitted_by=str(user.id), db=db)
    log_audit(db, user_id=user.id, action="UPDATED_FEEDBACK", entity_type="interview", entity_id=interview_id)
    db.commit()
    db.refresh(fb)
    return single(feedback_dict(fb))


@router.get("/{interview_id}/feedback")
def get_interview_feedback(
    interview_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    interview = db.get(Interview, _uuid(interview_id))
    if interview is None:
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
