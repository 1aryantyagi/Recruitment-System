"""Skill tables: skills (§9.4), skill_aliases (§9.5), candidate_skills (§9.8)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Enum as SAEnum,
    Float,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col
from app.models.enums import ProficiencyLevel, SkillCategory


class Skill(Base):
    __tablename__ = "skills"

    id = pk_col()
    name = Column(String(100), unique=True, nullable=False)
    category = Column(SAEnum(SkillCategory, name="skill_category"), nullable=False, default=SkillCategory.TOOL)
    # False for auto-created unrecognized skills pending admin review (§4.10).
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = created_at_col()

    aliases = relationship("SkillAlias", back_populates="skill", cascade="all, delete-orphan")


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id = pk_col()
    skill_id = fk_col("skills.id")
    alias = Column(String(100), unique=True, nullable=False, index=True)  # stored lowercase
    created_at = created_at_col()

    skill = relationship("Skill", back_populates="aliases")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id = pk_col()
    candidate_id = fk_col("candidates.id")
    skill_id = fk_col("skills.id")
    proficiency_level = Column(SAEnum(ProficiencyLevel, name="proficiency_level"), nullable=True)
    years_of_experience = Column(Float, nullable=True)
    # False = auto-extracted by LLM; True = confirmed by HR (§6.1).
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = created_at_col()

    skill = relationship("Skill")

    __table_args__ = (
        UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skill"),
        Index("ix_candidate_skills_skill_id", "skill_id"),
        Index("ix_candidate_skills_candidate_id", "candidate_id"),
    )
