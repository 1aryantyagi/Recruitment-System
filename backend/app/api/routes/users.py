"""User & interviewer management routes (§8.1 admin, §8.3 interviewers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import user_public
from app.core.auth import require_roles
from app.core.errors import BadRequestError
from app.core.responses import single
from app.core.security import hash_password
from app.database.base import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.api import CreateUserRequest

router = APIRouter(tags=["users"])


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
        raise BadRequestError("A user with this email already exists")
    user = User(name=body.name, email=str(body.email).lower(), role=role,
                password_hash=hash_password(body.password), is_interviewer=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return single(user_public(user))
