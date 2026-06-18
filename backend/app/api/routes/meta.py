"""Reference-data routes: domains, departments, pipeline status reasons.
Used to populate frontend dropdowns."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import department_dict, domain_dict, status_reason_dict
from app.core.auth import get_current_user, require_roles
from app.core.responses import single
from app.database.base import get_db
from app.models import Department, Domain, PipelineStatusReason, User
from app.models.enums import UserRole

router = APIRouter(tags=["meta"])


@router.get("/domains")
def list_domains(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(select(Domain).order_by(Domain.name)).scalars().all()
    return single([domain_dict(d) for d in rows])


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(select(Department).order_by(Department.name)).scalars().all()
    return single([department_dict(d) for d in rows])


@router.get("/status-reasons")
def list_status_reasons(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(PipelineStatusReason).where(PipelineStatusReason.is_active.is_(True))
    if status:
        stmt = stmt.where(PipelineStatusReason.status == status)
    rows = db.execute(stmt.order_by(PipelineStatusReason.status, PipelineStatusReason.reason)).scalars().all()
    return single([status_reason_dict(r) for r in rows])
