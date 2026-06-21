"""Auth-session tables: refresh_tokens.

A refresh token is a high-entropy opaque string handed to the client; only its
SHA-256 hash is stored here, so a DB read never exposes a usable token. Rotation
on every use plus reuse-detection (a presented-but-revoked token revokes the
whole family) gives stolen-token containment on top of the stateless access JWT.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = pk_col()
    user_id = fk_col("users.id", index=True)  # CASCADE: tokens die with the user
    token_hash = Column(String(64), nullable=False, unique=True, index=True)  # sha256 hex
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
