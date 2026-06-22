"""Authentication routes (§8.1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import user_public
from app.core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    issue_refresh_token,
    require_roles,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.core.errors import AuthenticationError, BadRequestError
from app.core.events import log_audit
from app.core.logging import get_logger
from app.core.security import hash_password
from app.database.base import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.api import CreateUserRequest, LoginRequest, LogoutRequest, RefreshRequest
from app.core.responses import single

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("route.auth")


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.email, body.password)
    if user is None:
        log.warning("route.auth.login_failed", email=body.email)
        raise AuthenticationError("Invalid email or password")
    access = create_access_token(user)
    refresh = issue_refresh_token(db, user)
    db.commit()
    log.info("route.auth.login_success", user_id=str(user.id), email=user.email, role=str(user.role))
    return single({
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_public(user),
    })


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh pair (rotation)."""
    user, new_refresh = rotate_refresh_token(db, body.refresh_token)
    access = create_access_token(user)
    db.commit()
    log.info("route.auth.refresh_rotated", user_id=str(user.id))
    return single({"access_token": access, "refresh_token": new_refresh, "token_type": "bearer"})


@router.post("/logout")
def logout(body: LogoutRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Stateless access JWT (client discards it); also revoke the refresh token
    # server-side when supplied so it can never be rotated again.
    if body.refresh_token:
        revoke_refresh_token(db, body.refresh_token)
        db.commit()
        log.info("route.auth.logout_revoked", user_id=str(user.id))
    return single({"success": True})


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return single(user_public(user))


@router.post("/users")
def create_user(
    body: CreateUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        role = UserRole(body.role)
    except ValueError as exc:
        raise BadRequestError(f"Invalid role: {body.role}") from exc
    if db.execute(select(User).filter_by(email=body.email.lower())).scalar_one_or_none():
        log.warning("route.auth.create_user_conflict", email=str(body.email).lower())
        raise BadRequestError("A user with this email already exists")
    user = User(
        name=body.name, email=str(body.email).lower(), role=role,
        password_hash=hash_password(body.password), is_interviewer=body.is_interviewer,
    )
    db.add(user)
    db.flush()
    log_audit(db, user_id=admin.id, action="CREATED_USER", entity_type="user", entity_id=user.id,
              ip_address=request.client.host if request.client else None)
    db.commit()
    log.info("route.auth.user_created", user_id=str(user.id), email=user.email,
             role=role.value, created_by=str(admin.id))
    return single(user_public(user))
