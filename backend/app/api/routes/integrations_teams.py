"""Admin routes for the domain → Microsoft Teams group mapping that drives
interview-feedback monitoring, plus a helper to list a team's channels and a
manual "poll now" trigger. All ADMIN-only.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import domain_teams_mapping_dict
from app.core.auth import require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.events import log_audit
from app.core.logging import get_logger
from app.core.responses import single
from app.database.base import get_db
from app.integrations.ms_graph import client as graph
from app.models import Domain, DomainTeamsMapping, User
from app.models.enums import UserRole
from app.schemas.api import CreateTeamsMappingRequest, UpdateTeamsMappingRequest

router = APIRouter(prefix="/integrations/teams", tags=["integrations"])
log = get_logger("route.integrations_teams")
_ADMIN = require_roles(UserRole.ADMIN)


@router.get("/mappings")
def list_mappings(db: Session = Depends(get_db), admin: User = Depends(_ADMIN)):
    rows = db.execute(
        select(DomainTeamsMapping).order_by(DomainTeamsMapping.created_at)
    ).scalars().all()
    return single([domain_teams_mapping_dict(m) for m in rows])


@router.post("/mappings")
def create_mapping(
    body: CreateTeamsMappingRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    did = _uuid(body.domain_id)
    if db.get(Domain, did) is None:
        raise NotFoundError("Domain not found")
    existing = db.execute(
        select(DomainTeamsMapping).where(DomainTeamsMapping.domain_id == did)
    ).scalar_one_or_none()
    if existing is not None:
        raise BadRequestError("A Teams mapping already exists for this domain")
    m = DomainTeamsMapping(
        domain_id=did,
        teams_group_name=body.teams_group_name,
        teams_team_id=body.teams_team_id,
        teams_channel_id=body.teams_channel_id,
        is_active=body.is_active,
    )
    db.add(m)
    db.flush()
    log_audit(db, user_id=admin.id, action="CREATED_TEAMS_MAPPING",
              entity_type="domain_teams_mapping", entity_id=m.id)
    db.commit()
    db.refresh(m)
    log.info("route.teams.mapping_created", mapping_id=str(m.id), domain_id=str(did),
             admin_id=str(admin.id))
    return single(domain_teams_mapping_dict(m))


@router.patch("/mappings/{mapping_id}")
def update_mapping(
    mapping_id: str,
    body: UpdateTeamsMappingRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    m = db.get(DomainTeamsMapping, _uuid(mapping_id))
    if m is None:
        raise NotFoundError("Teams mapping not found")
    data = body.model_dump(exclude_unset=True)
    for field in ("teams_group_name", "teams_team_id", "teams_channel_id", "is_active"):
        if field in data and data[field] is not None:
            setattr(m, field, data[field])
    log_audit(db, user_id=admin.id, action="UPDATED_TEAMS_MAPPING",
              entity_type="domain_teams_mapping", entity_id=m.id)
    db.commit()
    db.refresh(m)
    log.info("route.teams.mapping_updated", mapping_id=str(m.id), admin_id=str(admin.id))
    return single(domain_teams_mapping_dict(m))


@router.delete("/mappings/{mapping_id}")
def delete_mapping(
    mapping_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(_ADMIN),
):
    m = db.get(DomainTeamsMapping, _uuid(mapping_id))
    if m is None:
        raise NotFoundError("Teams mapping not found")
    db.delete(m)
    log_audit(db, user_id=admin.id, action="DELETED_TEAMS_MAPPING",
              entity_type="domain_teams_mapping", entity_id=mapping_id)
    db.commit()
    log.info("route.teams.mapping_deleted", mapping_id=mapping_id, admin_id=str(admin.id))
    return single({"deleted": True, "id": mapping_id})


@router.get("/channels")
def list_channels(
    team_id: str = Query(..., description="Microsoft Teams team (group) id"),
    admin: User = Depends(_ADMIN),
):
    """List a team's channels (admin setup helper). Empty when MS Graph is unconfigured."""
    return single({"channels": graph.list_channels(team_id)})


@router.post("/poll", status_code=status.HTTP_202_ACCEPTED)
def trigger_poll(background: BackgroundTasks, admin: User = Depends(_ADMIN)):
    """Run one feedback poll cycle now (detect → email/Teams ingest → reminders),
    in the background. For testing / on-demand collection."""
    from app.services.scheduler import poll_feedback

    background.add_task(poll_feedback)
    log.info("route.teams.poll_triggered", admin_id=str(admin.id))
    return single({"status": "ACCEPTED", "message": "Feedback poll triggered."})


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc
