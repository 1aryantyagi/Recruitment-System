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
import hashlib
import secrets
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AuthenticationError, UnauthorizedError
from app.core.logging import get_logger
from app.database.base import get_db
from app.models import RefreshToken, User
from app.models.enums import UserRole

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)
log = get_logger("core.auth")


def _role_str(user: User) -> str:
    return user.role.value if isinstance(user.role, UserRole) else str(user.role)


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
    try:
        payload = decode_token(creds.credentials)
    except AuthenticationError:
        log.warning("core.auth.token_invalid")
        raise
    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        log.warning("core.auth.token_malformed_subject")
        raise AuthenticationError("Malformed token subject") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        log.warning("core.auth.user_inactive_or_missing", user_id=str(user_id))
        raise AuthenticationError("User not found or inactive")
    log.debug("core.auth.token_decoded", user_id=str(user.id), role=_role_str(user))
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing that the caller has one of `roles`."""
    allowed = {r.value for r in roles}

    def _dep(user: User = Depends(get_current_user)) -> User:
        actual = _role_str(user)
        if actual not in allowed:
            log.warning(
                "core.auth.role_denied",
                user_id=str(user.id),
                actual_role=actual,
                required_roles=sorted(allowed),
            )
            raise UnauthorizedError(
                "Insufficient role for this operation",
                detail=f"requires one of {sorted(allowed)}",
            )
        log.debug(
            "core.auth.role_allowed",
            user_id=str(user.id),
            actual_role=actual,
            required_roles=sorted(allowed),
        )
        return user

    return _dep


def ensure_can_modify(user: User, *owner_ids: uuid.UUID | None) -> None:
    """Authorize a write against a specific record (horizontal access control).

    ADMIN may modify anything. Otherwise the caller must be one of the record's
    owners (creator / assigned manager / interviewer). Records with NO owner set
    — e.g. candidates ingested from email where `uploaded_by` is NULL — are
    treated as shared/org-owned and fall back to the route's role gate, so the
    team isn't locked out of system-created records.

    Reads are intentionally not gated here: the candidate/requisition pool is
    shared across the recruiting team; only mutations are owner-scoped.
    """
    if _role_str(user) == UserRole.ADMIN.value:
        return
    present = [oid for oid in owner_ids if oid is not None]
    if not present or user.id in present:
        return
    raise UnauthorizedError(
        "You can only modify records you own",
        detail="resource belongs to another user",
    )


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    from app.core.security import verify_password

    user = db.execute(select(User).filter_by(email=email.lower().strip())).scalar_one_or_none()
    if user is None or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# ---------------- Refresh tokens (rotation + revocation) ----------------
#
# The raw refresh token is a high-entropy opaque string returned to the client;
# only its SHA-256 hash is persisted, so a DB read never yields a usable token.
# Every successful refresh rotates the token (old one revoked, new one issued).
# Presenting an already-revoked token is treated as theft and revokes the whole
# family (all of that user's tokens), forcing a fresh login.

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user: User) -> str:
    """Mint a new refresh token for `user`, persist its hash, return the raw value.
    The caller is responsible for committing the surrounding transaction."""
    raw = secrets.token_urlsafe(48)
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user.id, token_hash=_hash_token(raw), expires_at=expires))
    db.flush()
    return raw


def rotate_refresh_token(db: Session, raw: str) -> tuple[User, str]:
    """Validate + rotate a refresh token. Returns (user, new_raw_refresh_token).

    Raises AuthenticationError on any invalid/expired/reused token. On reuse of a
    revoked token, all of the user's tokens are revoked (and committed) before
    raising, so a leaked token can't be replayed."""
    rt = db.execute(
        select(RefreshToken).filter_by(token_hash=_hash_token(raw))
    ).scalar_one_or_none()
    if rt is None:
        raise AuthenticationError("Invalid refresh token")

    now = dt.datetime.now(dt.timezone.utc)
    if rt.revoked_at is not None:
        # Reuse of a rotated/revoked token → assume compromise; nuke the family.
        revoke_all_for_user(db, rt.user_id)
        db.commit()
        raise AuthenticationError("Refresh token has already been used")
    if rt.expires_at <= now:
        raise AuthenticationError("Refresh token expired")

    user = db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    rt.revoked_at = now  # rotate: retire the presented token
    new_raw = issue_refresh_token(db, user)
    return user, new_raw


def revoke_refresh_token(db: Session, raw: str) -> None:
    """Best-effort single-token revocation (logout). Silent if unknown/already revoked.
    The caller commits."""
    rt = db.execute(
        select(RefreshToken).filter_by(token_hash=_hash_token(raw))
    ).scalar_one_or_none()
    if rt is not None and rt.revoked_at is None:
        rt.revoked_at = dt.datetime.now(dt.timezone.utc)


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    """Revoke every active refresh token for a user (logout-everywhere / theft response)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=dt.datetime.now(dt.timezone.utc))
    )
