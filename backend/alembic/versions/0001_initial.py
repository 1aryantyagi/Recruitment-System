"""initial schema (all 19 tables, §9)

The ORM models fully specify the schema — including the generated `tsvector`
column, the GIN index, the partial-unique index on `gmail_message_id`, and all
composite unique constraints — so this migration materializes the metadata
directly rather than duplicating column definitions.

Revision ID: 0001
Revises:
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

from app.database.base import Base
import app.models  # noqa: F401  (populate metadata)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
