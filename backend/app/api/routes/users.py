"""User & interviewer management routes (§8.1 admin, §8.3 interviewers)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import interviewer_slot_dict, user_public
from app.core.auth import require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.responses import single
from app.core.security import hash_password
from app.database.base import get_db
from app.models import InterviewerSlot, User
from app.models.enums import UserRole
from app.schemas.api import (
    CreateUserRequest,
    InterviewerSlotRequest,
    UpdateInterviewerSlotRequest,
)

router = APIRouter(tags=["users"])
log = get_logger("route.users")
_ADMIN = require_roles(UserRole.ADMIN)
_HR_DM_ADMIN = require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc


def _parse_hhmm(value: str) -> dt.time:
    try:
        h, m = (int(x) for x in str(value).split(":")[:2])
        return dt.time(hour=h, minute=m)
    except (ValueError, TypeError) as exc:
        raise BadRequestError("slot_time must be 'HH:MM'") from exc


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_roles(UserRole.ADMIN))):
    rows = db.execute(select(User).order_by(User.name)).scalars().all()
    return single([user_public(u) for u in rows])


@router.get("/interviewers")
def list_interviewers(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)),
):
    rows = db.execute(
        select(User).where(User.is_interviewer.is_(True), User.is_active.is_(True)).order_by(User.name)
    ).scalars().all()
    return single([user_public(u) for u in rows])


@router.post("/interviewers")
def create_interviewer(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        role = UserRole(body.role)
    except ValueError as exc:
        raise BadRequestError(f"Invalid role: {body.role}") from exc
    if db.execute(select(User).filter_by(email=str(body.email).lower())).scalar_one_or_none():
        log.warning("route.users.create_interviewer_conflict", email=str(body.email).lower())
        raise BadRequestError("A user with this email already exists")
    user = User(name=body.name, email=str(body.email).lower(), role=role,
                password_hash=hash_password(body.password), is_interviewer=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("route.users.interviewer_created", user_id=str(user.id), email=user.email,
             role=role.value, created_by=str(admin.id))
    return single(user_public(user))


# ---------------- Interviewer recurring slots (§8.3) ----------------
def _require_interviewer(db: Session, interviewer_id: str) -> User:
    u = db.get(User, _uuid(interviewer_id))
    if u is None or not u.is_interviewer:
        raise NotFoundError("Interviewer not found")
    return u


@router.get("/interviewers/{interviewer_id}/slots")
def list_interviewer_slots(
    interviewer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    _require_interviewer(db, interviewer_id)
    rows = db.execute(
        select(InterviewerSlot).where(InterviewerSlot.interviewer_id == _uuid(interviewer_id))
        .order_by(InterviewerSlot.slot_time)
    ).scalars().all()
    return single([interviewer_slot_dict(s) for s in rows])


@router.post("/interviewers/{interviewer_id}/slots")
def create_interviewer_slot(
    interviewer_id: str,
    body: InterviewerSlotRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    _require_interviewer(db, interviewer_id)
    slot_time = _parse_hhmm(body.slot_time)
    if db.execute(select(InterviewerSlot).filter_by(
            interviewer_id=_uuid(interviewer_id), slot_time=slot_time)).scalar_one_or_none():
        log.warning("route.users.create_slot_conflict", interviewer_id=interviewer_id,
                    slot_time=str(slot_time))
        raise BadRequestError("A slot at that time already exists for this interviewer")
    slot = InterviewerSlot(
        interviewer_id=_uuid(interviewer_id), slot_time=slot_time,
        weekday_mask=body.weekday_mask, duration_minutes=body.duration_minutes, is_active=True,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    log.info("route.users.slot_created", slot_id=str(slot.id), interviewer_id=interviewer_id,
             slot_time=str(slot_time), created_by=str(admin.id))
    return single(interviewer_slot_dict(slot))


@router.patch("/interviewers/{interviewer_id}/slots/{slot_id}")
def update_interviewer_slot(
    interviewer_id: str,
    slot_id: str,
    body: UpdateInterviewerSlotRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    slot = db.get(InterviewerSlot, _uuid(slot_id))
    if slot is None or str(slot.interviewer_id) != str(_uuid(interviewer_id)):
        log.warning("route.users.update_slot.not_found", interviewer_id=interviewer_id, slot_id=slot_id)
        raise NotFoundError("Slot not found")
    data = body.model_dump(exclude_unset=True)
    if "slot_time" in data and data["slot_time"] is not None:
        slot.slot_time = _parse_hhmm(data.pop("slot_time"))
    for k, v in data.items():
        if v is not None:
            setattr(slot, k, v)
    db.commit()
    db.refresh(slot)
    log.info("route.users.slot_updated", slot_id=str(slot.id), interviewer_id=interviewer_id,
             updated_by=str(admin.id))
    return single(interviewer_slot_dict(slot))


@router.delete("/interviewers/{interviewer_id}/slots/{slot_id}")
def delete_interviewer_slot(
    interviewer_id: str,
    slot_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    slot = db.get(InterviewerSlot, _uuid(slot_id))
    if slot is not None and str(slot.interviewer_id) == str(_uuid(interviewer_id)):
        db.delete(slot)
        db.commit()
        log.info("route.users.slot_deleted", slot_id=slot_id, interviewer_id=interviewer_id,
                 deleted_by=str(admin.id))
    return single({"status": "deleted"})
