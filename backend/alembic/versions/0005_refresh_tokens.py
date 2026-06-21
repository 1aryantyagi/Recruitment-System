"""add refresh_tokens table (rotation + revocation for the auth session layer)

Stores only the SHA-256 hash of each issued refresh token, with rotation and
revocation timestamps. Fresh DBs already materialize this table via `0001`'s
`Base.metadata.create_all`, so creation is guarded on existence to stay
idempotent for both fresh and existing databases (same pattern as `0004`).

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_TABLE = "refresh_tokens"


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE):  # fresh DBs got it from create_all in 0001
        return
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Mirror the ORM indexes/constraints (create_all renders these names).
    op.create_index("ix_refresh_tokens_user_id", _TABLE, ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", _TABLE, ["token_hash"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    op.drop_index("ix_refresh_tokens_token_hash", table_name=_TABLE)
    op.drop_index("ix_refresh_tokens_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
