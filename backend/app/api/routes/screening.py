"""Telephonic screening routes (§8.5)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.telephonic_screening import start_call
from app.api.serializers import call_dict
from app.core.auth import require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit
from app.core.responses import Pagination, list_envelope, pagination_params, single
from app.database.base import get_db
from app.models import Candidate, CallLog, User
from app.models.enums import UserRole
from app.schemas.api import StartCallRequest
from app.services import flow

router = APIRouter(tags=["screening"])


@router.post("/screening/start-call")
def start_screening_call(
    body: StartCallRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR)),
):
    cand = db.get(Candidate, _uuid(body.candidate_id))
    if cand is None:
        raise NotFoundError("Candidate not found")

    result = start_call(candidate_id=body.candidate_id, requisition_id=body.requisition_id,
                        initiated_by=str(user.id))
    log_audit(db, user_id=user.id, action="STARTED_SCREENING_CALL", entity_type="candidate",
              entity_id=cand.id, metadata={"call_log_id": result.get("call_log_id")})
    db.commit()

    # In mock mode there is no live Twilio call/webhook — process immediately so
    # the screening flow completes end-to-end with a mock transcript.
    if result.get("mock") and result.get("call_log_id"):
        background.add_task(flow.run_screening_processing, result["call_log_id"], None)

    return single({**result, "status": "INITIATED"})


@router.get("/screening/{candidate_id}/calls")
def list_calls(
    candidate_id: str,
    pagination: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)),
):
    stmt = select(CallLog).where(CallLog.candidate_id == _uuid(candidate_id)).order_by(CallLog.called_at.desc())
    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    return list_envelope([call_dict(c) for c in rows], total, pagination.page, pagination.limit)


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc
