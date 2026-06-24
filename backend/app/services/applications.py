"""Shared JobApplication status-advancement helper.

Centralizes the forward-only status transition + `application_status_history`
row that several flows need (scheduling, screening, feedback collection), so the
rank guard lives in one place. Mirrors the inline logic in
`agents.interview_scheduling.emit_analytics` and `telephonic_screening`.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import JobApplication
from app.models.enums import ApplicationStatus
from app.models.logs import ApplicationStatusHistory

log = get_logger("services.applications")

# Forward-only rank for the "happy path". Terminal-negative statuses (REJECTED,
# WITHDRAWN) are handled as a branch, not by rank.
_STATUS_RANK = {
    ApplicationStatus.NEW: 0,
    ApplicationStatus.SCREENING: 1,
    ApplicationStatus.SHORTLISTED: 2,
    ApplicationStatus.INTERVIEW_SCHEDULED: 3,
    ApplicationStatus.OFFERED: 4,
    ApplicationStatus.HIRED: 5,
}
_TERMINAL = {ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN, ApplicationStatus.HIRED}


def advance_application_status(
    db: Session,
    application: JobApplication | None,
    to_status: ApplicationStatus,
    *,
    reason: str | None = None,
    changed_by: uuid.UUID | None = None,
) -> bool:
    """Move `application` to `to_status` with guards + a history row. Returns True
    only if the status actually changed. The caller owns the transaction (commit).

    Guards:
      • never changes an application already in a terminal status (REJECTED /
        WITHDRAWN / HIRED);
      • REJECTED / WITHDRAWN are reachable from any non-terminal status;
      • ranked targets (SCREENING…HIRED) advance only to a strictly higher rank
        (no regression, no no-op)."""
    if application is None:
        return False
    current = application.status
    if current in _TERMINAL:
        log.debug("application.advance.skip_terminal", application_id=str(application.id),
                  current=current.value)
        return False
    if to_status == current:
        return False
    if to_status in (ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN):
        allowed = True
    else:
        allowed = _STATUS_RANK.get(to_status, -1) > _STATUS_RANK.get(current, -1)
    if not allowed:
        log.debug("application.advance.skip_rank", application_id=str(application.id),
                  current=current.value, target=to_status.value)
        return False

    application.status = to_status
    if to_status == ApplicationStatus.REJECTED and reason:
        application.rejection_reason = reason
    db.add(ApplicationStatusHistory(
        application_id=application.id,
        from_status=current,
        to_status=to_status,
        reason_note=reason,
        changed_by=changed_by,
    ))
    db.flush()
    log.info("application.advance", application_id=str(application.id),
             from_status=current.value, to_status=to_status.value)
    return True
