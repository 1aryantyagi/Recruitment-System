"""Shared utilities for the LangGraph agents (§7.0 conventions)."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Skill, SkillAlias
from app.models.enums import ProficiencyLevel, SkillCategory


@lru_cache
def get_checkpointer():
    """In-process checkpointer for async agents. Swap for a Postgres/SQLite
    saver in production for cross-restart durability."""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def map_proficiency(value: str | None) -> ProficiencyLevel | None:
    if not value:
        return None
    v = value.strip().upper()
    return {
        "BEGINNER": ProficiencyLevel.BEGINNER,
        "INTERMEDIATE": ProficiencyLevel.INTERMEDIATE,
        "EXPERT": ProficiencyLevel.EXPERT,
        "ADVANCED": ProficiencyLevel.EXPERT,
    }.get(v)


def normalize_skill(db: Session, raw_name: str) -> tuple[Skill | None, bool]:
    """Resolve a raw skill string to a canonical Skill via skill_aliases (§4.10).

    Returns (skill, is_new). Unrecognized skills are created with
    is_verified=False and an alias added so future occurrences resolve.
    """
    alias = (raw_name or "").strip().lower()
    if not alias:
        return None, False

    row = db.execute(select(SkillAlias).filter_by(alias=alias)).scalar_one_or_none()
    if row:
        return db.get(Skill, row.skill_id), False

    existing = db.execute(select(Skill).where(func.lower(Skill.name) == alias)).scalar_one_or_none()
    if existing:
        _ensure_alias(db, existing.id, alias)
        return existing, False

    skill = Skill(name=raw_name.strip()[:100], category=SkillCategory.TOOL, is_verified=False)
    db.add(skill)
    db.flush()
    _ensure_alias(db, skill.id, alias)
    return skill, True


def _ensure_alias(db: Session, skill_id, alias: str) -> None:
    try:
        with db.begin_nested():
            db.add(SkillAlias(skill_id=skill_id, alias=alias))
    except IntegrityError:
        pass  # alias already exists (concurrent insert) — fine
