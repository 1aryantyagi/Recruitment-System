"""interview feedback collection (Teams mapping, feedback requests + messages)

Adds the post-interview feedback workflow:
  • ``domain_teams_mappings``        — domain → Teams group/channel + poll cursor
  • ``interview_feedback_requests``  — per-interview monitoring state + email tracking
  • ``interview_feedback_messages``  — append-only log of collected feedback (any source)
plus a ``source`` column on ``interview_feedback`` and the new enum types
(``feedback_request_status``, ``feedback_source``).

Fresh DBs already materialize these via ``0001``'s ``Base.metadata.create_all``, so
every step here is guarded on existence to stay idempotent for both fresh and
existing databases.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_MAPPINGS = "domain_teams_mappings"
_REQUESTS = "interview_feedback_requests"
_MESSAGES = "interview_feedback_messages"
_MSG_IDX = "uq_feedback_message_source_id"


def _has_index(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table):
        return False
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def _has_column(insp, table: str, col: str) -> bool:
    if not insp.has_table(table):
        return False
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # New enum types — no-op if already present (e.g. created by 0001 on a fresh DB).
    postgresql.ENUM("AWAITING", "RECEIVED", "ESCALATED",
                    name="feedback_request_status").create(bind, checkfirst=True)
    postgresql.ENUM("TEAMS", "EMAIL", "FORM", "AI_ANALYSIS",
                    name="feedback_source").create(bind, checkfirst=True)

    # create_type=False: the types are created above (or by 0001); columns just reference them.
    frs = postgresql.ENUM("AWAITING", "RECEIVED", "ESCALATED",
                          name="feedback_request_status", create_type=False)
    fsrc = postgresql.ENUM("TEAMS", "EMAIL", "FORM", "AI_ANALYSIS",
                           name="feedback_source", create_type=False)
    reco = postgresql.ENUM("STRONG_YES", "YES", "MAYBE", "NO", "STRONG_NO",
                           name="recommendation", create_type=False)  # existing type

    if not insp.has_table(_MAPPINGS):
        op.create_table(
            _MAPPINGS,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("domain_id", UUID(as_uuid=True),
                      sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("teams_group_name", sa.String(200), nullable=False),
            sa.Column("teams_team_id", sa.String(200), nullable=False),
            sa.Column("teams_channel_id", sa.String(200), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not insp.has_table(_REQUESTS):
        op.create_table(
            _REQUESTS,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("interview_id", UUID(as_uuid=True),
                      sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("status", frs, nullable=False, server_default="AWAITING"),
            sa.Column("source", fsrc, nullable=True),
            sa.Column("gmail_thread_id", sa.String(200), nullable=True),
            sa.Column("original_message_id", sa.String(998), nullable=True),
            sa.Column("sent_message_id", sa.String(200), nullable=True),
            sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("awaiting_since", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(f"ix_{_REQUESTS}_status", _REQUESTS, ["status"])
        op.create_index(f"ix_{_REQUESTS}_gmail_thread_id", _REQUESTS, ["gmail_thread_id"])

    if not insp.has_table(_MESSAGES):
        op.create_table(
            _MESSAGES,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("interview_id", UUID(as_uuid=True),
                      sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source", fsrc, nullable=False),
            sa.Column("author_name", sa.String(200), nullable=True),
            sa.Column("author_email", sa.String(255), nullable=True),
            sa.Column("raw_feedback", sa.Text(), nullable=True),
            sa.Column("recommendation", reco, nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("extracted", JSONB, nullable=True),
            sa.Column("source_message_id", sa.String(255), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(f"ix_{_MESSAGES}_interview_id", _MESSAGES, ["interview_id"])

    # Partial unique index for idempotent message ingestion (also model-declared).
    if not _has_index(bind, _MESSAGES, _MSG_IDX):
        op.create_index(_MSG_IDX, _MESSAGES, ["source_message_id"], unique=True,
                        postgresql_where=sa.text("source_message_id IS NOT NULL"))

    # interview_feedback.source — graceful add for existing DBs.
    if not _has_column(insp, "interview_feedback", "source"):
        op.add_column("interview_feedback", sa.Column("source", fsrc, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _has_column(insp, "interview_feedback", "source"):
        op.drop_column("interview_feedback", "source")
    for tbl in (_MESSAGES, _REQUESTS, _MAPPINGS):
        if insp.has_table(tbl):
            op.drop_table(tbl)
    postgresql.ENUM(name="feedback_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="feedback_request_status").drop(bind, checkfirst=True)
