"""add call_logs.qualified (live in-call qualification judgement)

The Realtime voice agent decides mid-call whether a candidate qualifies for an
interview round. That judgement is stored here so the post-call evaluation can
treat an explicit False as authoritative (soft-defer: no auto-SHORTLIST) and so a
candidate the call already booked isn't regressed.

NULL = not decided live (legacy / IVR calls).

Fresh DBs already materialize this column via ``0001``'s create_all, so the add
is guarded on column existence to stay idempotent.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_TABLE = "call_logs"
_COL = "qualified"


def _has_column(bind, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE) and not _has_column(bind, _TABLE, _COL):
        op.add_column(_TABLE, sa.Column(_COL, sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE) and _has_column(bind, _TABLE, _COL):
        op.drop_column(_TABLE, _COL)
