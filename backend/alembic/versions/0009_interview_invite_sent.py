"""add interviews.invite_sent (calendar invite delivery flag)

Interview invites are emailed to the candidate as an .ics via Gmail. This flag
records whether that invite actually went out: False means the interview row
exists but no invite was delivered (Gmail unconfigured, send failed, or no real
candidate email), so HR can follow up / resend instead of assuming success.

Fresh DBs already materialize this column via ``0001``'s create_all, so the add
is guarded on column existence to stay idempotent.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_TABLE = "interviews"
_COL = "invite_sent"


def _has_column(bind, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE) and not _has_column(bind, _TABLE, _COL):
        op.add_column(
            _TABLE,
            sa.Column(_COL, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE) and _has_column(bind, _TABLE, _COL):
        op.drop_column(_TABLE, _COL)
