"""Analytics routes (§8.7) — served by Agent 7."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agents import analytics as a7
from app.core.auth import require_roles
from app.core.errors import NotFoundError
from app.core.responses import single
from app.database.base import get_db
from app.models import User
from app.models.enums import UserRole

router = APIRouter(prefix="/analytics", tags=["analytics"])
_HR_DM_ADMIN = require_roles(UserRole.HR, UserRole.DELIVERY_MANAGER, UserRole.ADMIN)


@router.get("/dashboard")
def dashboard(
    summary: bool = Query(default=False, description="Include an LLM natural-language digest"),
    db: Session = Depends(get_db),
    user: User = Depends(_HR_DM_ADMIN),
):
    data = a7.dashboard(db)
    if summary:
        data["digest"] = a7.digest(db)
    return single(data)


@router.get("/funnel")
def funnel(db: Session = Depends(get_db), user: User = Depends(_HR_DM_ADMIN)):
    return single(a7.funnel(db))


@router.get("/sources")
def sources(db: Session = Depends(get_db), user: User = Depends(_HR_DM_ADMIN)):
    return single(a7.sources(db))


@router.get("/time-to-hire")
def time_to_hire(db: Session = Depends(get_db), user: User = Depends(_HR_DM_ADMIN)):
    return single(a7.time_to_hire(db))


@router.get("/requisitions/{requisition_id}")
def requisition_analytics(requisition_id: str, db: Session = Depends(get_db), user: User = Depends(_HR_DM_ADMIN)):
    data = a7.requisition_analytics(db, requisition_id)
    if not data:
        raise NotFoundError("Requisition not found")
    return single(data)
