"""Requisition routes (§8.3)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.common import normalize_skill
from app.agents.resume_scoring import run_scoring_for_requisition
from app.api.routes.candidates import build_candidate_query
from app.api.serializers import (
    candidate_list_item,
    requisition_dict,
    requisition_interviewer_dict,
    score_dict,
)
from app.core.auth import ensure_can_modify, require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit
from app.core.logging import get_logger
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.models import (
    Candidate,
    CandidateScore,
    Requisition,
    RequisitionInterviewer,
    RequisitionSkill,
    User,
)
from app.models.enums import (
    RequisitionStatus,
    SeniorityLevel,
    ShiftPreference,
    UserRole,
    WorkMode,
)
from app.schemas.api import (
    AssignInterviewerRequest,
    CreateRequisitionRequest,
    UpdateRequisitionRequest,
)
from app.services.interview_slots import get_open_slots

router = APIRouter(prefix="/requisitions", tags=["requisitions"])
log = get_logger("route.requisitions")
_HR_DM_ADMIN = require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)


def _enum_or_none(cls, value):
    if not value:
        return None
    try:
        return cls(value)
    except ValueError as exc:
        raise BadRequestError(f"Invalid value '{value}' for {cls.__name__}") from exc


def _uuid_or_none(value):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc


@router.post("")
def create_requisition(
    body: CreateRequisitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER)),
):
    req = Requisition(
        title=body.title,
        description=body.description,
        domain_id=_uuid_or_none(body.domain_id),
        department_id=_uuid_or_none(body.department_id),
        seniority_level=_enum_or_none(SeniorityLevel, body.seniority_level),
        location=body.location,
        work_mode=_enum_or_none(WorkMode, body.work_mode),
        shift_timing=_enum_or_none(ShiftPreference, body.shift_timing),
        min_experience_years=body.min_experience_years,
        max_experience_years=body.max_experience_years,
        min_budget_ctc=body.min_budget_ctc,
        max_budget_ctc=body.max_budget_ctc,
        number_of_openings=body.number_of_openings,
        status=RequisitionStatus.OPEN,
        created_by=user.id,
        hiring_manager_id=_uuid_or_none(body.hiring_manager_id),
        target_close_date=_date(body.target_close_date),
    )
    db.add(req)
    db.flush()

    for s in body.skills:
        skill_id = _uuid_or_none(s.skill_id)
        if skill_id is None and s.skill_name:
            skill, _ = normalize_skill(db, s.skill_name)
            skill_id = skill.id if skill else None
        if skill_id is None:
            continue
        exists = db.execute(
            select(RequisitionSkill).filter_by(requisition_id=req.id, skill_id=skill_id)
        ).scalar_one_or_none()
        if not exists:
            db.add(RequisitionSkill(requisition_id=req.id, skill_id=skill_id,
                                    is_mandatory=s.is_mandatory, minimum_years=s.minimum_years))
    log_audit(db, user_id=user.id, action="CREATED_REQUISITION", entity_type="requisition", entity_id=req.id,
              ip_address=request.client.host if request.client else None)
    db.commit()
    req_id = str(req.id)

    # Score the eligible candidate pool against the new requisition (Agent 2, dual trigger).
    log.info("route.requisitions.create.dispatch_background", requisition_id=req_id,
             title=req.title, created_by=str(user.id))
    try:
        run_scoring_for_requisition(req_id)
    except Exception:
        log.warning("route.requisitions.create.scoring_failed", requisition_id=req_id, exc_info=True)

    fresh = db.get(Requisition, req.id)
    return single(requisition_dict(db, fresh, detail=True))


@router.get("")
def list_requisitions(
    pagination: Pagination = Depends(pagination_params),
    status: str | None = Query(default=None),
    domain_id: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    stmt = select(Requisition)
    if status:
        stmt = stmt.where(Requisition.status == _enum_or_none(RequisitionStatus, status))
    if domain_id:
        stmt = stmt.where(Requisition.domain_id == _uuid_or_none(domain_id))
    if department_id:
        stmt = stmt.where(Requisition.department_id == _uuid_or_none(department_id))
    stmt = stmt.order_by(Requisition.created_at.desc())

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    log.debug("route.requisitions.list", total=total, returned=len(rows), status=status)
    return list_envelope([requisition_dict(db, r) for r in rows], total, pagination.page, pagination.limit)


@router.get("/{requisition_id}")
def get_requisition(requisition_id: str, db: Session = Depends(get_db), user: User = Depends(_HR_DM_ADMIN)):
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.get.not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    return single(requisition_dict(db, req, detail=True))


@router.patch("/{requisition_id}")
def update_requisition(
    requisition_id: str,
    body: UpdateRequisitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER)),
):
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.update.not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    ensure_can_modify(user, req.created_by, req.hiring_manager_id)
    data = body.model_dump(exclude_unset=True)
    status_changed = None
    if "status" in data and data["status"]:
        req.status = _enum_or_none(RequisitionStatus, data.pop("status"))
        status_changed = req.status.value if req.status else None
    if "work_mode" in data and data["work_mode"]:
        req.work_mode = _enum_or_none(WorkMode, data.pop("work_mode"))
    if "hiring_manager_id" in data:
        req.hiring_manager_id = _uuid_or_none(data.pop("hiring_manager_id"))
    if "target_close_date" in data:
        req.target_close_date = _date(data.pop("target_close_date"))
    for k, v in data.items():
        setattr(req, k, v)
    log_audit(db, user_id=user.id, action="UPDATED_REQUISITION", entity_type="requisition", entity_id=req.id)
    db.commit()
    db.refresh(req)
    if status_changed is not None:
        log.info("route.requisitions.status_changed", requisition_id=str(req.id),
                 new_status=status_changed, updated_by=str(user.id))
    return single(requisition_dict(db, req, detail=True))


@router.get("/{requisition_id}/candidates")
def requisition_candidates(
    requisition_id: str,
    pagination: Pagination = Depends(pagination_params),
    skills: list[str] | None = Query(default=None),
    min_exp: float | None = Query(default=None),
    max_exp: float | None = Query(default=None),
    stage: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    """Scored candidate pool for this requisition, ranked by match_score (§4.7)."""
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.candidates.not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    stmt = build_candidate_query(
        db, skills=skills, min_exp=min_exp, max_exp=max_exp, search=search, stage=stage,
        scope_requisition_id=requisition_id,
    )
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()

    score_map = {
        str(s.candidate_id): s for s in db.execute(
            select(CandidateScore).where(CandidateScore.requisition_id == req.id)
        ).scalars()
    }
    items = []
    for c in rows:
        item = candidate_list_item(c)
        sc = score_map.get(str(c.id))
        item["match_score"] = sc.total_score if sc else None
        item["score_breakdown"] = score_dict(sc) if sc else None
        items.append(item)
    return list_envelope(items, total, pagination.page, pagination.limit)


# ---------------- Interviewer assignment & availability ----------------
@router.get("/{requisition_id}/interviewers")
def list_requisition_interviewers(
    requisition_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    """Interviewers assigned to conduct rounds for this requisition."""
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.list_interviewers.not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    rows = db.execute(
        select(RequisitionInterviewer, User)
        .join(User, User.id == RequisitionInterviewer.interviewer_id)
        .where(RequisitionInterviewer.requisition_id == req.id)
        .order_by(User.name)
    ).all()
    return single([requisition_interviewer_dict(ri, u) for ri, u in rows])


@router.post("/{requisition_id}/interviewers")
def assign_interviewer(
    requisition_id: str,
    body: AssignInterviewerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.assign_interviewer.req_not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    ensure_can_modify(user, req.created_by, req.hiring_manager_id)
    interviewer = db.get(User, _uuid_or_none(body.interviewer_id))
    if interviewer is None or not interviewer.is_interviewer:
        log.warning("route.requisitions.assign_interviewer.invalid_interviewer",
                    requisition_id=requisition_id, interviewer_id=body.interviewer_id)
        raise BadRequestError("interviewer_id must reference an active interviewer")
    existing = db.execute(
        select(RequisitionInterviewer).filter_by(requisition_id=req.id, interviewer_id=interviewer.id)
    ).scalar_one_or_none()
    ri = existing or RequisitionInterviewer(requisition_id=req.id, interviewer_id=interviewer.id)
    if existing is None:
        db.add(ri)
        log_audit(db, user_id=user.id, action="ASSIGNED_INTERVIEWER", entity_type="requisition",
                  entity_id=req.id, metadata={"interviewer_id": str(interviewer.id)})
        db.commit()
        db.refresh(ri)
        log.info("route.requisitions.interviewer_assigned", requisition_id=str(req.id),
                 interviewer_id=str(interviewer.id), assigned_by=str(user.id))
    return single(requisition_interviewer_dict(ri, interviewer))


@router.delete("/{requisition_id}/interviewers/{interviewer_id}")
def unassign_interviewer(
    requisition_id: str,
    interviewer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.unassign_interviewer.req_not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    ensure_can_modify(user, req.created_by, req.hiring_manager_id)
    ri = db.execute(
        select(RequisitionInterviewer).filter_by(
            requisition_id=req.id, interviewer_id=_uuid_or_none(interviewer_id))
    ).scalar_one_or_none()
    if ri is not None:
        db.delete(ri)
        log_audit(db, user_id=user.id, action="UNASSIGNED_INTERVIEWER", entity_type="requisition",
                  entity_id=req.id, metadata={"interviewer_id": interviewer_id})
        db.commit()
        log.info("route.requisitions.interviewer_unassigned", requisition_id=str(req.id),
                 interviewer_id=interviewer_id, unassigned_by=str(user.id))
    return single({"status": "removed"})


@router.get("/{requisition_id}/open-slots")
def list_open_slots(
    requisition_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    """Free interview slots for this requisition within the bookable window
    (current week; Fri/weekend → next week). Powers both the HR UI and the
    voice agent."""
    req = db.get(Requisition, _uuid_or_none(requisition_id))
    if req is None:
        log.warning("route.requisitions.open_slots.not_found", requisition_id=requisition_id)
        raise NotFoundError("Requisition not found")
    slots = get_open_slots(db, requisition_id=req.id)
    log.debug("route.requisitions.open_slots", requisition_id=str(req.id), slot_count=len(slots))
    return single([s.to_dict() for s in slots])


def _date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
