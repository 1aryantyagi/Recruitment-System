"""Job-application routes — pipeline board read + stage moves.

Powers the ATS Kanban board: ``GET /applications`` returns a board-ready,
joined view (one query populates a whole board) and ``PATCH /applications/{id}``
persists a drag-and-drop stage move, appending an ``application_status_history``
row and emitting a ``STATUS_CHANGED`` analytics event — mirroring the existing
blacklist flow in ``candidates.py``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.serializers import user_public
from app.core.auth import ensure_can_modify, require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit, log_event
from app.core.logging import get_logger
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.models import (
    Candidate,
    CandidateScore,
    Interview,
    JobApplication,
    Requisition,
    User,
)
from app.models.enums import ApplicationStatus, EventType, UserRole
from app.models.logs import ApplicationStatusHistory
from app.schemas.api import UpdateApplicationStatusRequest

router = APIRouter(prefix="/applications", tags=["applications"])
log = get_logger("route.applications")
_HR_DM_ADMIN = require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc


@router.get("")
def list_applications(
    pagination: Pagination = Depends(pagination_params),
    requisition_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, description="Candidate name (partial match)"),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    """Board-ready application list (joined with candidate, requisition, score, owner).

    One call populates an entire Kanban board. Filter by `requisition_id` for a
    single-job board, or omit it for an all-openings board.
    """
    stmt = (
        select(JobApplication, Candidate, Requisition, CandidateScore, User)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .join(Requisition, Requisition.id == JobApplication.requisition_id)
        .join(
            CandidateScore,
            and_(
                CandidateScore.candidate_id == JobApplication.candidate_id,
                CandidateScore.requisition_id == JobApplication.requisition_id,
            ),
            isouter=True,
        )
        .join(User, User.id == JobApplication.created_by, isouter=True)
        .where(Candidate.is_blacklisted.is_(False))
    )
    if requisition_id:
        stmt = stmt.where(JobApplication.requisition_id == _uuid(requisition_id))
    if status:
        stmt = stmt.where(JobApplication.status == _validate_status(status))
    if search:
        stmt = stmt.where(Candidate.full_name.ilike(f"%{search}%"))
    stmt = stmt.order_by(JobApplication.match_score.desc().nullslast(),
                         JobApplication.updated_at.desc())

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).all()

    # Latest interview per (candidate, requisition) — one query, mapped in Python.
    cand_ids = {r[1].id for r in rows}
    latest: dict[tuple, Interview] = {}
    if cand_ids:
        interviews = db.execute(
            select(Interview)
            .where(Interview.candidate_id.in_(cand_ids))
            .order_by(Interview.round_number.desc(), Interview.scheduled_at.desc())
        ).scalars().all()
        for iv in interviews:
            key = (iv.candidate_id, iv.requisition_id)
            latest.setdefault(key, iv)  # first seen wins (already ordered latest-first)

    items = [
        _board_item(app, cand, req, score, owner, latest.get((cand.id, req.id)))
        for (app, cand, req, score, owner) in rows
    ]
    log.debug("route.applications.list", total=total, returned=len(items),
              requisition_id=requisition_id, status=status)
    return list_envelope(items, total, pagination.page, pagination.limit)


@router.patch("/{application_id}")
def update_application_status(
    application_id: str,
    body: UpdateApplicationStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.ADMIN)),
):
    """Persist a pipeline stage move (Kanban drag-and-drop)."""
    app_row = db.get(JobApplication, _uuid(application_id))
    if app_row is None:
        log.warning("route.applications.update.not_found", application_id=application_id)
        raise NotFoundError("Application not found")
    ensure_can_modify(user, app_row.created_by)

    target = _validate_status(body.status)
    prev = app_row.status
    if prev == target:
        return single(_detail_item(db, app_row))

    app_row.status = target
    if target == ApplicationStatus.REJECTED and body.reason_note:
        app_row.rejection_reason = body.reason_note
    db.add(ApplicationStatusHistory(
        application_id=app_row.id,
        from_status=prev,
        to_status=target,
        reason_id=_uuid(body.reason_id) if body.reason_id else None,
        reason_note=body.reason_note,
        changed_by=user.id,
    ))
    # Funnel-relevant events for Agent 7 analytics.
    log_event(db, EventType.STATUS_CHANGED, candidate_id=app_row.candidate_id,
              requisition_id=app_row.requisition_id, triggered_by=user.id,
              metadata={"from": prev.value if prev else None, "to": target.value})
    if target == ApplicationStatus.HIRED:
        log_event(db, EventType.HIRED, candidate_id=app_row.candidate_id,
                  requisition_id=app_row.requisition_id, triggered_by=user.id)
    elif target == ApplicationStatus.REJECTED:
        log_event(db, EventType.REJECTED, candidate_id=app_row.candidate_id,
                  requisition_id=app_row.requisition_id, triggered_by=user.id)
    log_audit(db, user_id=user.id, action="CHANGED_APPLICATION_STATUS",
              entity_type="job_application", entity_id=app_row.id,
              metadata={"from": prev.value if prev else None, "to": target.value})
    db.commit()
    db.refresh(app_row)
    log.info("route.applications.status_changed", application_id=str(app_row.id),
             from_status=prev.value if prev else None, to_status=target.value,
             changed_by=str(user.id))
    return single(_detail_item(db, app_row))


def _validate_status(value: str) -> ApplicationStatus:
    try:
        return ApplicationStatus(value)
    except ValueError as exc:
        raise BadRequestError(f"Invalid application status: {value}") from exc


def _board_item(app: JobApplication, cand: Candidate, req: Requisition,
                score: CandidateScore | None, owner: User | None,
                interview: Interview | None) -> dict:
    return {
        "id": str(app.id),
        "status": app.status.value if hasattr(app.status, "value") else app.status,
        "match_score": app.match_score,
        "rejection_reason": app.rejection_reason,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        "candidate": {
            "id": str(cand.id),
            "full_name": cand.full_name,
            "current_designation": cand.current_designation,
            "current_company": cand.current_company,
            "current_location": cand.current_location,
            "total_experience_years": cand.total_experience_years,
        },
        "requisition": {"id": str(req.id), "title": req.title},
        "resume_score": score.total_score if score else None,
        "owner": user_public(owner),
        "latest_interview": None if interview is None else {
            "id": str(interview.id),
            "status": interview.status.value if hasattr(interview.status, "value") else interview.status,
            "round_type": interview.round_type.value if hasattr(interview.round_type, "value") else interview.round_type,
            "ai_overall_rating": interview.ai_overall_rating,
        },
    }


def _detail_item(db: Session, app: JobApplication) -> dict:
    """Re-fetch the joined board item for a single application (after a write)."""
    cand = db.get(Candidate, app.candidate_id)
    req = db.get(Requisition, app.requisition_id)
    score = db.execute(
        select(CandidateScore).where(
            CandidateScore.candidate_id == app.candidate_id,
            CandidateScore.requisition_id == app.requisition_id,
        )
    ).scalars().first()
    owner = db.get(User, app.created_by) if app.created_by else None
    interview = db.execute(
        select(Interview).where(
            Interview.candidate_id == app.candidate_id,
            Interview.requisition_id == app.requisition_id,
        ).order_by(Interview.round_number.desc(), Interview.scheduled_at.desc())
    ).scalars().first()
    return _board_item(app, cand, req, score, owner, interview)
