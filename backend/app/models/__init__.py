"""Import all models so Base.metadata is fully populated (used by create_all
and Alembic). Re-exports the common model classes."""
from app.models.candidate import Candidate, CandidateResume
from app.models.interview import CallLog, Interview, InterviewFeedback
from app.models.logs import (
    AnalyticsEvent,
    ApplicationStatusHistory,
    AuditLog,
    PipelineStatusReason,
)
from app.models.org import Department, Domain, User
from app.models.requisition import (
    CandidateScore,
    JobApplication,
    Requisition,
    RequisitionSkill,
)
from app.models.skill import CandidateSkill, Skill, SkillAlias

__all__ = [
    "User",
    "Domain",
    "Department",
    "Skill",
    "SkillAlias",
    "CandidateSkill",
    "Candidate",
    "CandidateResume",
    "Requisition",
    "RequisitionSkill",
    "JobApplication",
    "CandidateScore",
    "CallLog",
    "Interview",
    "InterviewFeedback",
    "AnalyticsEvent",
    "AuditLog",
    "PipelineStatusReason",
    "ApplicationStatusHistory",
]
