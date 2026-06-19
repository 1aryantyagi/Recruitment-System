"""add candidate_detail_requests table (auto-collected logistics fields)

Tracks the email auto-sent to a candidate asking for the logistics fields their
resume omitted (current/expected CTC, notice period, availability, shift and
work-mode preference), plus the parsed reply once it arrives. Fresh DBs already
materialize this table and its `detail_request_status` enum via `0001`'s
`Base.metadata.create_all`, so creation is guarded on existence to stay
idempotent for both fresh and existing databases.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLE = "candidate_detail_requests"
_ENUM = "detail_request_status"
_STATUSES = ("SENT", "RECEIVED", "FAILED")


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE):  # fresh DBs got it from create_all in 0001
        return
    # create_type=False — we create the enum explicitly (checkfirst) so the
    # column definition below just references the existing type.
    status_enum = ENUM(*_STATUSES, name=_ENUM, create_type=False)
    status_enum.create(bind, checkfirst=True)
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id", UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("gmail_thread_id", sa.String(length=200), nullable=True),
        sa.Column("original_message_id", sa.String(length=998), nullable=True),
        sa.Column("sent_message_id", sa.String(length=200), nullable=True),
        sa.Column("requested_fields", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", status_enum, nullable=False, server_default="SENT"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_raw_text", sa.Text(), nullable=True),
        sa.Column("parsed_values", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Mirror the `index=True` columns from the ORM model (create_all renders
    # these as `ix_<table>_<column>`).
    op.create_index("ix_candidate_detail_requests_candidate_id", _TABLE, ["candidate_id"])
    op.create_index("ix_candidate_detail_requests_gmail_thread_id", _TABLE, ["gmail_thread_id"])
    op.create_index("ix_candidate_detail_requests_status", _TABLE, ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    op.drop_index("ix_candidate_detail_requests_status", table_name=_TABLE)
    op.drop_index("ix_candidate_detail_requests_gmail_thread_id", table_name=_TABLE)
    op.drop_index("ix_candidate_detail_requests_candidate_id", table_name=_TABLE)
    op.drop_table(_TABLE)
    ENUM(name=_ENUM).drop(bind, checkfirst=True)
