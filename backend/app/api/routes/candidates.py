"""Candidate routes (§8.2) + dynamic filtering (§10)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agents.resume_intake import run_intake
from app.agents.resume_scoring import run_scoring_for_candidate
from app.api.serializers import candidate_detail, candidate_list_item
from app.core.auth import ensure_can_modify, get_current_user, require_roles
from app.core.errors import AppError, BadRequestError, NotFoundError, UnauthorizedError
from app.core.events import log_audit, log_event
from app.core.logging import get_logger
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.integrations.storage import local as storage
from app.models import (
    Candidate,
    CandidateResume,
    CandidateScore,
    CandidateSkill,
    JobApplication,
    User,
)
from app.models.enums import ApplicationStatus, CandidateSource, EventType, UserRole, WorkMode
from app.models.logs import ApplicationStatusHistory
from app.agents.common import normalize_skill
from app.schemas.api import BlacklistRequest, ConfirmSkillsRequest, UpdateCandidateRequest

router = APIRouter(prefix="/candidates", tags=["candidates"])
log = get_logger("route.candidates")

_ACTIVE_STATUSES = [
    ApplicationStatus.NEW, ApplicationStatus.SCREENING, ApplicationStatus.SHORTLISTED,
    ApplicationStatus.INTERVIEW_SCHEDULED, ApplicationStatus.OFFERED,
]


def build_candidate_query(
    db: Session,
    *,
    skills: list[str] | None = None,
    min_exp: float | None = None,
    max_exp: float | None = None,
    domain_id: str | None = None,
    notice_period_max: int | None = None,
    work_mode: str | None = None,
    location: str | None = None,
    source: str | None = None,
    search: str | None = None,
    stage: str | None = None,
    blacklisted: bool = False,
    scope_requisition_id: str | None = None,
):
    """Compose the dynamic candidate query (§10). All filters AND-combined."""
    stmt = select(Candidate).where(Candidate.is_blacklisted.is_(blacklisted))

    if min_exp is not None:
        stmt = stmt.where(Candidate.total_experience_years >= min_exp)
    if max_exp is not None:
        stmt = stmt.where(Candidate.total_experience_years <= max_exp)
    if domain_id:
        stmt = stmt.where(Candidate.domain_id == uuid.UUID(domain_id))
    if notice_period_max is not None:
        stmt = stmt.where(Candidate.notice_period_days <= notice_period_max)
    if work_mode:
        stmt = stmt.where(Candidate.work_mode_preference == WorkMode(work_mode))
    if location:
        stmt = stmt.where(Candidate.current_location.ilike(f"%{location}%"))
    if source:
        stmt = stmt.where(Candidate.source == CandidateSource(source))

    if search:
        # Full-text search over resume content (tsvector + plainto_tsquery).
        sub = (
            select(CandidateResume.candidate_id)
            .where(CandidateResume.search_vector.op("@@")(func.plainto_tsquery("english", search)))
        )
        stmt = stmt.where(Candidate.id.in_(sub))

    if scope_requisition_id:
        rid = uuid.UUID(scope_requisition_id)
        stmt = stmt.join(CandidateScore, CandidateScore.candidate_id == Candidate.id).where(
            CandidateScore.requisition_id == rid
        )
        if stage:
            app_sub = select(JobApplication.candidate_id).where(
                JobApplication.requisition_id == rid,
                JobApplication.status == ApplicationStatus(stage),
            )
            stmt = stmt.where(Candidate.id.in_(app_sub))

    if skills:
        skill_uuids = [uuid.UUID(s) for s in skills]
        stmt = (
            stmt.join(CandidateSkill, CandidateSkill.candidate_id == Candidate.id)
            .where(CandidateSkill.skill_id.in_(skill_uuids))
            .group_by(Candidate.id)
            .having(func.count(func.distinct(CandidateSkill.skill_id)) == len(skill_uuids))
        )

    # Ordering: by match_score desc when scoped to a requisition; else recency.
    if scope_requisition_id:
        order_col = func.max(CandidateScore.total_score) if skills else CandidateScore.total_score
        stmt = stmt.order_by(order_col.desc())
    else:
        stmt = stmt.order_by(Candidate.created_at.desc())
    return stmt


@router.post("")
def upload_candidates(
    request: Request,
    files: list[UploadFile] = File(...),
    email: str | None = Form(default=None),
    full_name: str | None = Form(default=None),
    source: str = Form(default="EMAIL"),
    source_detail: str | None = Form(default=None),
    user: User = Depends(require_roles(UserRole.HR)),
):
    """Upload one or many resumes. Each file is processed independently (§6.1)."""
    log.info("route.candidates.upload.dispatch_background", file_count=len(files),
             source=source, uploaded_by=str(user.id))
    results = []
    for f in files:
        content = f.file.read()
        overrides = {}
        if email and len(files) == 1:
            overrides["email"] = email
        if full_name and len(files) == 1:
            overrides["full_name"] = full_name
        try:
            res = run_intake(
                file_content=content, file_name=f.filename or "resume",
                mime_type=f.content_type or "", source=source, uploaded_by=str(user.id),
                source_detail=source_detail, overrides=overrides,
            )
            # Score the new candidate against eligible open requisitions (Agent 2).
            if res.get("candidate_id"):
                try:
                    run_scoring_for_candidate(res["candidate_id"])
                except Exception:
                    log.warning("route.candidates.upload.scoring_failed",
                                candidate_id=res.get("candidate_id"), exc_info=True)
            results.append({"filename": f.filename, **res})
        except AppError as exc:
            log.warning("route.candidates.upload.intake_failed",
                        filename=f.filename, error=exc.code, message=exc.message)
            results.append({"filename": f.filename, "error": exc.code, "message": exc.message, "detail": exc.detail})

    # Audit (best-effort).
    db = next(get_db())
    try:
        log_audit(db, user_id=user.id, action="UPLOADED_RESUME", entity_type="candidate",
                  entity_id=results[0].get("candidate_id") if results else None,
                  metadata={"count": len(files)}, ip_address=request.client.host if request.client else None)
        db.commit()
    finally:
        db.close()
    return single({"results": results})


@router.post("/{candidate_id}/resume")
def upload_resume_version(
    candidate_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    """Add a new resume version to an existing candidate (max 3 — §4.4)."""
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.resume_version.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    ensure_can_modify(user, cand.uploaded_by)
    content = file.file.read()
    log.info("route.candidates.resume_version.dispatch_background",
             candidate_id=candidate_id, uploaded_by=str(user.id))
    res = run_intake(
        file_content=content, file_name=file.filename or "resume",
        mime_type=file.content_type or "", uploaded_by=str(user.id),
        existing_candidate_id=candidate_id,
    )
    return single(res)


@router.post("/{candidate_id}/confirm-skills")
def confirm_skills(
    candidate_id: str,
    body: ConfirmSkillsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.confirm_skills.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    ensure_can_modify(user, cand.uploaded_by)
    # Confirm
    for sid in body.confirmed_skill_ids:
        cs = db.execute(select(CandidateSkill).filter_by(candidate_id=cand.id, skill_id=_uuid(sid))).scalar_one_or_none()
        if cs:
            cs.is_verified = True
    # Remove false positives
    for sid in body.removed_skill_ids:
        cs = db.execute(select(CandidateSkill).filter_by(candidate_id=cand.id, skill_id=_uuid(sid))).scalar_one_or_none()
        if cs:
            db.delete(cs)
    # Add missed skills (confirmed immediately)
    for name in body.added_skill_names:
        skill, _ = normalize_skill(db, name)
        if skill is None:
            continue
        exists = db.execute(select(CandidateSkill).filter_by(candidate_id=cand.id, skill_id=skill.id)).scalar_one_or_none()
        if exists:
            exists.is_verified = True
        else:
            db.add(CandidateSkill(candidate_id=cand.id, skill_id=skill.id, is_verified=True))
    log_event(db, EventType.SKILLS_CONFIRMED, candidate_id=cand.id, triggered_by=user.id)
    log_audit(db, user_id=user.id, action="CONFIRMED_SKILLS", entity_type="candidate", entity_id=cand.id)
    db.commit()
    db.refresh(cand)
    log.info("route.candidates.skills_confirmed", candidate_id=str(cand.id),
             confirmed=len(body.confirmed_skill_ids), removed=len(body.removed_skill_ids),
             added=len(body.added_skill_names), confirmed_by=str(user.id))
    return single(candidate_detail(db, cand))


@router.get("")
def list_candidates(
    pagination: Pagination = Depends(pagination_params),
    skills: list[str] | None = Query(default=None),
    min_exp: float | None = Query(default=None),
    max_exp: float | None = Query(default=None),
    domain_id: str | None = Query(default=None),
    notice_period_max: int | None = Query(default=None),
    work_mode: str | None = Query(default=None),
    location: str | None = Query(default=None),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    blacklisted: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if blacklisted and user.role != UserRole.ADMIN:
        log.warning("route.candidates.list.blacklist_forbidden", user_id=str(user.id), role=str(user.role))
        raise UnauthorizedError("Only Admin can view blacklisted candidates")
    if user.role not in (UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN):
        log.warning("route.candidates.list.forbidden", user_id=str(user.id), role=str(user.role))
        raise UnauthorizedError("Insufficient role")
    stmt = build_candidate_query(
        db, skills=skills, min_exp=min_exp, max_exp=max_exp, domain_id=domain_id,
        notice_period_max=notice_period_max, work_mode=work_mode, location=location,
        source=source, search=search, stage=stage, blacklisted=blacklisted,
    )
    rows, total = _paginate(db, stmt, pagination)
    log.debug("route.candidates.list", total=total, returned=len(rows),
              blacklisted=blacklisted, search=search)
    return list_envelope([candidate_list_item(c) for c in rows], total, pagination.page, pagination.limit)


@router.get("/{candidate_id}")
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)),
):
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.get.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    return single(candidate_detail(db, cand))


@router.patch("/{candidate_id}")
def update_candidate(
    candidate_id: str,
    body: UpdateCandidateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.update.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    ensure_can_modify(user, cand.uploaded_by)
    data = body.model_dump(exclude_unset=True)
    if "work_mode_preference" in data and data["work_mode_preference"]:
        data["work_mode_preference"] = WorkMode(data["work_mode_preference"])
    if "domain_id" in data and data["domain_id"]:
        data["domain_id"] = _uuid(data["domain_id"])
    for k, v in data.items():
        setattr(cand, k, v)
    log_audit(db, user_id=user.id, action="UPDATED_CANDIDATE", entity_type="candidate", entity_id=cand.id)
    db.commit()
    db.refresh(cand)
    return single(candidate_detail(db, cand))


@router.get("/{candidate_id}/resume")
def get_resume_url(
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)),
):
    resume = db.execute(
        select(CandidateResume).where(CandidateResume.candidate_id == _uuid(candidate_id))
        .order_by(CandidateResume.is_latest.desc(), CandidateResume.uploaded_at.desc())
    ).scalars().first()
    if resume is None or not resume.file_url:
        log.warning("route.candidates.resume_url.not_found", candidate_id=candidate_id)
        raise NotFoundError("No resume file available")
    log.info("route.candidates.resume_url.issued", candidate_id=candidate_id, user_id=str(user.id))
    return single({"url": storage.signed_url(resume.file_url)})


@router.post("/{candidate_id}/blacklist")
def blacklist_candidate(
    candidate_id: str,
    body: BlacklistRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.ADMIN)),
):
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.blacklist.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    ensure_can_modify(user, cand.uploaded_by)
    cand.is_blacklisted = True
    cand.blacklist_reason_id = _uuid(body.reason_id) if body.reason_id else None
    cand.blacklisted_by = user.id
    cand.blacklisted_at = dt.datetime.now(dt.timezone.utc)
    cand.blacklist_note = body.note
    # Drop all active pipeline applications with a system note.
    apps = db.execute(
        select(JobApplication).where(JobApplication.candidate_id == cand.id,
                                     JobApplication.status.in_(_ACTIVE_STATUSES))
    ).scalars().all()
    for app in apps:
        prev = app.status
        app.status = ApplicationStatus.WITHDRAWN
        db.add(ApplicationStatusHistory(application_id=app.id, from_status=prev,
                                        to_status=ApplicationStatus.WITHDRAWN, reason_note="Candidate blacklisted"))
    log_event(db, EventType.BLACKLISTED, candidate_id=cand.id, triggered_by=user.id)
    log_audit(db, user_id=user.id, action="BLACKLISTED_CANDIDATE", entity_type="candidate", entity_id=cand.id,
              metadata={"dropped_applications": len(apps)}, ip_address=request.client.host if request.client else None)
    db.commit()
    db.refresh(cand)
    log.info("route.candidates.blacklisted", candidate_id=str(cand.id),
             dropped_applications=len(apps), blacklisted_by=str(user.id))
    return single(candidate_detail(db, cand))


@router.delete("/{candidate_id}/blacklist")
def unblacklist_candidate(
    candidate_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cand = db.get(Candidate, _uuid(candidate_id))
    if cand is None:
        log.warning("route.candidates.unblacklist.not_found", candidate_id=candidate_id)
        raise NotFoundError("Candidate not found")
    cand.is_blacklisted = False
    cand.blacklist_reason_id = None
    cand.blacklisted_by = None
    cand.blacklisted_at = None
    cand.blacklist_note = None
    log_audit(db, user_id=user.id, action="REMOVED_BLACKLIST", entity_type="candidate", entity_id=cand.id,
              ip_address=request.client.host if request.client else None)
    db.commit()
    db.refresh(cand)
    log.info("route.candidates.unblacklisted", candidate_id=str(cand.id), removed_by=str(user.id))
    return single(candidate_detail(db, cand))


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc


def _paginate(db: Session, stmt, pagination: Pagination):
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    return list(rows), int(total)
