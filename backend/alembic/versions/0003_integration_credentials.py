"""add integration_credentials table (encrypted OAuth token storage)

Stores per-provider OAuth credentials (Gmail) so re-authorization is a one-time
admin action instead of editing `.env`. Fresh DBs already materialize this table
via `0001`'s `Base.metadata.create_all`, so creation is guarded on existence to
stay idempotent for both fresh and existing databases.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLE = "integration_credentials"


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE):  # fresh DBs got it from create_all in 0001
        return
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("auth_mode", sa.String(length=30), nullable=True),
        sa.Column("connected_email", sa.String(length=255), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Mirror `Column(provider, unique=True, index=True)` from the ORM model, which
    # create_all renders as a single unique index of this exact name.
    op.create_index(
        "ix_integration_credentials_provider", _TABLE, ["provider"], unique=True
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    op.drop_index("ix_integration_credentials_provider", table_name=_TABLE)
    op.drop_table(_TABLE)
