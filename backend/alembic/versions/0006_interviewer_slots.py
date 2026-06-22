"""add interviewer scheduling tables (requisition_interviewers, interviewer_slots)

Turns bare interviewer ``users`` rows into a bookable calendar:
  • ``requisition_interviewers`` — interviewers assigned to a requisition.
  • ``interviewer_slots`` — each interviewer's recurring weekday availability.

Also adds a partial UNIQUE index on ``interviews(interviewer_id, scheduled_at)``
for live rounds, as a DB-level guard against double-booking.

Fresh DBs already materialize the two tables (and the model-declared index) via
``0001``'s ``Base.metadata.create_all``, so every step here is guarded on
existence to stay idempotent for both fresh and existing databases.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_REQ_INT = "requisition_interviewers"
_SLOTS = "interviewer_slots"
_INTERVIEW_IDX = "uq_interview_slot_per_interviewer"
_WEEKDAYS_MON_FRI = 31  # Mon–Fri bitmask (date.weekday() positions)


def _has_index(bind, table: str, name: str) -> bool:
    return any(ix["name"] == name for ix in inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_REQ_INT):
        op.create_table(
            _REQ_INT,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("requisition_id", UUID(as_uuid=True),
                      sa.ForeignKey("requisitions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("interviewer_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("requisition_id", "interviewer_id", name="uq_requisition_interviewer"),
        )
        op.create_index(f"ix_{_REQ_INT}_requisition_id", _REQ_INT, ["requisition_id"])
        op.create_index(f"ix_{_REQ_INT}_interviewer_id", _REQ_INT, ["interviewer_id"])

    if not insp.has_table(_SLOTS):
        op.create_table(
            _SLOTS,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("interviewer_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slot_time", sa.Time(timezone=False), nullable=False),
            sa.Column("weekday_mask", sa.SmallInteger(), nullable=False,
                      server_default=str(_WEEKDAYS_MON_FRI)),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("interviewer_id", "slot_time", name="uq_interviewer_slot_time"),
        )
        op.create_index(f"ix_{_SLOTS}_interviewer_id", _SLOTS, ["interviewer_id"])

    # Partial unique index on the existing interviews table (defense-in-depth
    # against double-booking). Guarded so re-runs / fresh DBs are no-ops.
    if insp.has_table("interviews") and not _has_index(bind, "interviews", _INTERVIEW_IDX):
        op.create_index(
            _INTERVIEW_IDX,
            "interviews",
            ["interviewer_id", "scheduled_at"],
            unique=True,
            postgresql_where=sa.text(
                "status IN ('SCHEDULED','RESCHEDULED') "
                "AND scheduled_at IS NOT NULL AND interviewer_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("interviews") and _has_index(bind, "interviews", _INTERVIEW_IDX):
        op.drop_index(_INTERVIEW_IDX, table_name="interviews")
    if insp.has_table(_SLOTS):
        op.drop_table(_SLOTS)
    if insp.has_table(_REQ_INT):
        op.drop_table(_REQ_INT)
