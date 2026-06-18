"""Append-only event + audit helpers (REQ-DP-13).

`analytics_events` powers pipeline/funnel reporting (Agent 7); `audit_logs`
records user-initiated, record-mutating actions for accountability. Neither is
ever updated or deleted.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AnalyticsEvent, AuditLog
from app.models.enums import EventType


def log_event(
    db: Session,
    event_type: EventType | str,
    *,
    candidate_id: uuid.UUID | None = None,
    requisition_id: uuid.UUID | None = None,
    triggered_by: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AnalyticsEvent:
    """Append an analytics event. The caller is responsible for committing."""
    ev = AnalyticsEvent(
        event_type=event_type.value if isinstance(event_type, EventType) else str(event_type),
        candidate_id=candidate_id,
        requisition_id=requisition_id,
        triggered_by=triggered_by,
        event_metadata=metadata or {},
    )
    db.add(ev)
    return ev


def log_audit(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Append an audit-log record. The caller is responsible for committing."""
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        audit_metadata=metadata or {},
        ip_address=ip_address,
    )
    db.add(log)
    return log
