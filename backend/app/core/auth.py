"""Authentication & RBAC (§4.8, §5.5).

Local-dev replacement for Supabase Auth: email/password login issues a JWT
(HS256, signed with SECRET_KEY) carrying the user id and role claim. Every
protected route resolves the current user from the bearer token; `require_roles`
enforces the role claim before any business logic.

An optional Microsoft SSO path verifies an MS-issued token and matches the
user by email — active only when MS Graph credentials are configured.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AuthenticationError, UnauthorizedError
from app.database.base import get_db
from app.models import User
from app.models.enums import UserRole

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
        "name": user.name,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token", detail=str(exc)) from exc


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise AuthenticationError("Authentication required")
    payload = decode_token(creds.credentials)
    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("Malformed token subject") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing that the caller has one of `roles`."""
    allowed = {r.value for r in roles}

    def _dep(user: User = Depends(get_current_user)) -> User:
        role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        if role not in allowed:
            raise UnauthorizedError(
                "Insufficient role for this operation",
                detail=f"requires one of {sorted(allowed)}",
            )
        return user

    return _dep


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    from app.core.security import verify_password

    user = db.execute(select(User).filter_by(email=email.lower().strip())).scalar_one_or_none()
    if user is None or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
