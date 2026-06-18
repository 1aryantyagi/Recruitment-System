"""Authentication routes (§8.1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import user_public
from app.core.auth import authenticate_user, create_access_token, get_current_user, require_roles
from app.core.errors import AuthenticationError, BadRequestError
from app.core.events import log_audit
from app.core.security import hash_password
from app.database.base import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.api import CreateUserRequest, LoginRequest
from app.core.responses import single

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.email, body.password)
    if user is None:
        raise AuthenticationError("Invalid email or password")
    token = create_access_token(user)
    return single({"access_token": token, "token_type": "bearer", "user": user_public(user)})


@router.post("/logout")
def logout(_: User = Depends(get_current_user)):
    # Stateless JWT — client discards the token.
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
    return single(user_public(user))
