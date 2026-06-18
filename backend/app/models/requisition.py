"""Requisition tables: requisitions (§9.9), requisition_skills (§9.10),
job_applications (§9.11), candidate_scores (§9.12)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Enum as SAEnum,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col, updated_at_col
from app.models.enums import (
    ApplicationStatus,
    RequisitionStatus,
    SeniorityLevel,
    application_status_enum,
    shift_preference_enum,
    work_mode_enum,
)


class Requisition(Base):
    __tablename__ = "requisitions"

    id = pk_col()
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    domain_id = fk_col("domains.id", nullable=True, index=True)
    department_id = fk_col("departments.id", nullable=True)
    seniority_level = Column(SAEnum(SeniorityLevel, name="seniority_level"), nullable=True)
    location = Column(String(200), nullable=True)
    work_mode = Column(work_mode_enum, nullable=True)
    shift_timing = Column(shift_preference_enum, nullable=True)
    min_experience_years = Column(Float, nullable=True)
    max_experience_years = Column(Float, nullable=True)
    min_budget_ctc = Column(Integer, nullable=True)
    max_budget_ctc = Column(Integer, nullable=True)
    number_of_openings = Column(Integer, nullable=False, default=1)
    status = Column(SAEnum(RequisitionStatus, name="requisition_status"), nullable=False, default=RequisitionStatus.OPEN, index=True)
    created_by = fk_col("users.id", nullable=True)
    hiring_manager_id = fk_col("users.id", nullable=True)
    target_close_date = Column(Date, nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    domain = relationship("Domain")
    department = relationship("Department")
    skills = relationship("RequisitionSkill", back_populates="requisition", cascade="all, delete-orphan")


class RequisitionSkill(Base):
    __tablename__ = "requisition_skills"

    id = pk_col()
    requisition_id = fk_col("requisitions.id")
    skill_id = fk_col("skills.id")
    is_mandatory = Column(Boolean, nullable=False, default=True)
    minimum_years = Column(Float, nullable=True)
    created_at = created_at_col()

    requisition = relationship("Requisition", back_populates="skills")
    skill = relationship("Skill")

    __table_args__ = (UniqueConstraint("requisition_id", "skill_id", name="uq_requisition_skill"),)


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    requisition_id = fk_col("requisitions.id", index=True)
    status = Column(application_status_enum, nullable=False, default=ApplicationStatus.NEW, index=True)
    match_score = Column(Float, nullable=True, index=True)
    rejection_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = fk_col("users.id", nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        UniqueConstraint("candidate_id", "requisition_id", name="uq_application_candidate_requisition"),
    )


class CandidateScore(Base):
    __tablename__ = "candidate_scores"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    requisition_id = fk_col("requisitions.id", index=True)
    total_score = Column(Float, nullable=False, default=0.0)
    skills_score = Column(Float, nullable=False, default=0.0)
    experience_score = Column(Float, nullable=False, default=0.0)
    skills_depth_score = Column(Float, nullable=False, default=0.0)
    location_score = Column(Float, nullable=False, default=0.0)
    notice_period_score = Column(Float, nullable=False, default=0.0)
    scoring_version = Column(String(20), nullable=False, default="v1")
    created_at = created_at_col()

    __table_args__ = (
        UniqueConstraint("candidate_id", "requisition_id", name="uq_score_candidate_requisition"),
    )
