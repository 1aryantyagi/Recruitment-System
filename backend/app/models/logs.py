"""Log & reference tables: analytics_events (§9.16), audit_logs (§9.17),
pipeline_status_reasons (§9.18), application_status_history (§9.19).

analytics_events and audit_logs are append-only (REQ-DP-13)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col
from app.models.enums import application_status_enum


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = pk_col()
    event_type = Column(String(100), nullable=False, index=True)
    candidate_id = fk_col("candidates.id", nullable=True, index=True)
    requisition_id = fk_col("requisitions.id", nullable=True, index=True)
    triggered_by = fk_col("users.id", nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=True)
    occurred_at = created_at_col()

    __table_args__ = (Index("ix_analytics_events_occurred_at", "occurred_at"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = pk_col()
    user_id = fk_col("users.id", nullable=True)
    action = Column(String(200), nullable=False)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(String(100), nullable=True)
    audit_metadata = Column("metadata", JSONB, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = created_at_col()


class PipelineStatusReason(Base):
    __tablename__ = "pipeline_status_reasons"

    id = pk_col()
    # Vocabulary spans application statuses + special categories (DROPPED,
    # L1_REJECTED, ..., BLACKLISTED) — stored as text for flexibility (§9.18).
    status = Column(String(50), nullable=False, index=True)
    reason = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = created_at_col()


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id = pk_col()
    application_id = fk_col("job_applications.id", index=True)
    from_status = Column(application_status_enum, nullable=True)
    to_status = Column(application_status_enum, nullable=False)
    reason_id = fk_col("pipeline_status_reasons.id", nullable=True)
    reason_note = Column(Text, nullable=True)
    changed_by = fk_col("users.id", nullable=True)
    changed_at = created_at_col()
