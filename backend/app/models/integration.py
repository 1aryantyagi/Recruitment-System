"""Integration credential storage.

Holds per-provider OAuth credentials (currently Gmail) so re-authorization is a
one-time admin action rather than editing `.env`. Tokens are encrypted at rest
via `EncryptedString` (same pattern as `Candidate.phone`); the encryption key
never lives in the DB.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, String, Text

from app.database.base import Base
from app.models.common import created_at_col, pk_col, updated_at_col
from app.models.types import EncryptedString


class IntegrationCredential(Base):
    """One row per integration provider (unique `provider`)."""

    __tablename__ = "integration_credentials"

    id = pk_col()
    provider = Column(String(50), nullable=False, unique=True, index=True)  # e.g. "gmail"
    auth_mode = Column(String(30), nullable=True)        # "oauth_db" (SA/env modes are not stored here)
    connected_email = Column(String(255), nullable=True)  # mailbox this credential reads
    refresh_token = Column(EncryptedString, nullable=True)  # encrypted at rest
    access_token = Column(EncryptedString, nullable=True)   # encrypted at rest (cached short-lived token)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(Text, nullable=True)                  # space-delimited granted scopes
    # When auth fails (e.g. invalid_grant), the row is disabled so polling stops
    # retrying/log-spamming until an admin reconnects.
    disabled = Column(Boolean, nullable=False, default=False)
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at = created_at_col()
    updated_at = updated_at_col()
