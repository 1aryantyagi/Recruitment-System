"""Skill master routes (§8.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.serializers import skill_dict
from app.core.auth import get_current_user, require_roles
from app.core.errors import BadRequestError, NotFoundError
from app.core.responses import single
from app.database.base import get_db
from app.models import Skill, SkillAlias, User
from app.models.enums import SkillCategory, UserRole
from app.schemas.api import AddAliasRequest, CreateSkillRequest

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Full skills master list grouped by category (populates filter dropdowns)."""
    skills = db.execute(select(Skill).order_by(Skill.category, Skill.name)).scalars().all()
    grouped: dict[str, list] = {}
    for s in skills:
        grouped.setdefault(s.category.value if hasattr(s.category, "value") else str(s.category), []).append(skill_dict(s))
    return single({"by_category": grouped, "count": len(skills)})


@router.post("")
def create_skill(body: CreateSkillRequest, db: Session = Depends(get_db),
                 admin: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        category = SkillCategory(body.category)
    except ValueError as exc:
        raise BadRequestError(f"Invalid category: {body.category}") from exc
    if db.execute(select(Skill).where(Skill.name.ilike(body.name))).scalar_one_or_none():
        raise BadRequestError("Skill already exists")
    skill = Skill(name=body.name.strip(), category=category, is_verified=True)
    db.add(skill)
    db.flush()
    db.add(SkillAlias(skill_id=skill.id, alias=body.name.strip().lower()))
    db.commit()
    db.refresh(skill)
    return single(skill_dict(skill))


@router.post("/{skill_id}/aliases")
def add_aliases(skill_id: str, body: AddAliasRequest, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(UserRole.ADMIN))):
    skill = db.get(Skill, _uuid(skill_id))
    if skill is None:
        raise NotFoundError("Skill not found")
    added = []
    for alias in body.aliases:
        a = alias.strip().lower()
        if not a:
            continue
        try:
            with db.begin_nested():
                db.add(SkillAlias(skill_id=skill.id, alias=a))
            added.append(a)
        except IntegrityError:
            pass
    db.commit()
    return single({"skill_id": str(skill.id), "added_aliases": added})


def _uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid id") from exc
