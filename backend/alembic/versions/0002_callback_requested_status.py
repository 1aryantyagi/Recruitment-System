"""add CALLBACK_REQUESTED to call_status enum

The conversational screening agent ends a call as CALLBACK_REQUESTED when the
candidate says it isn't a good time, so HR can re-initiate later. Fresh DBs pick
this value up via create_all; existing DBs need the enum value added in place.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ permits ALTER TYPE ... ADD VALUE inside a transaction; the new
    # value just can't be referenced until the transaction commits (we don't).
    op.execute("ALTER TYPE call_status ADD VALUE IF NOT EXISTS 'CALLBACK_REQUESTED'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enum types; removing the value would require
    # rebuilding the type. Left as a no-op — the unused value is harmless.
    pass
