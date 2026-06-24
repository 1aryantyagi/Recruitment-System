"""All enumerations used by the data model (§9). Member name == value so the
stored representation is stable and human-readable."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    HR = "HR"
    DELIVERY_MANAGER = "DELIVERY_MANAGER"
    ADMIN = "ADMIN"


class SkillCategory(str, enum.Enum):
    PROGRAMMING_LANGUAGE = "PROGRAMMING_LANGUAGE"
    FRAMEWORK = "FRAMEWORK"
    CLOUD = "CLOUD"
    DATABASE = "DATABASE"
    TOOL = "TOOL"
    DOMAIN_SKILL = "DOMAIN_SKILL"
    SOFT_SKILL = "SOFT_SKILL"


class ProficiencyLevel(str, enum.Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    EXPERT = "EXPERT"


class WorkMode(str, enum.Enum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"


class ShiftPreference(str, enum.Enum):
    DAY = "DAY"
    NIGHT = "NIGHT"
    FLEXIBLE = "FLEXIBLE"


class CandidateSource(str, enum.Enum):
    LINKEDIN = "LINKEDIN"
    NAUKRI = "NAUKRI"
    EMAIL = "EMAIL"
    REFERRAL = "REFERRAL"
    GMAIL = "GMAIL"
    OTHER = "OTHER"


class DetailRequestStatus(str, enum.Enum):
    """candidate_detail_requests.status — lifecycle of an auto-sent request for
    the logistics fields missing from a resume (CTC, notice, availability, etc.)."""

    SENT = "SENT"          # email sent, awaiting the candidate's reply
    RECEIVED = "RECEIVED"  # reply parsed and applied to the candidate record
    FAILED = "FAILED"      # the outbound send failed


class SeniorityLevel(str, enum.Enum):
    INTERN = "INTERN"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"


class RequisitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ApplicationStatus(str, enum.Enum):
    NEW = "NEW"
    SCREENING = "SCREENING"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    HIRED = "HIRED"


class CallStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NO_ANSWER = "NO_ANSWER"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"  # candidate asked to be called back; HR may re-initiate


class RoundType(str, enum.Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    HR = "HR"
    FINAL = "FINAL"
    TECHNICAL = "TECHNICAL"
    CULTURAL = "CULTURAL"


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    RESCHEDULED = "RESCHEDULED"


class Recommendation(str, enum.Enum):
    STRONG_YES = "STRONG_YES"
    YES = "YES"
    MAYBE = "MAYBE"
    NO = "NO"
    STRONG_NO = "STRONG_NO"


class FeedbackRequestStatus(str, enum.Enum):
    """interview_feedback_requests.status — lifecycle of an interview's automated
    feedback-collection cycle (Teams + email monitoring)."""

    AWAITING = "AWAITING"     # interview concluded; monitoring Teams + email for feedback
    RECEIVED = "RECEIVED"     # a valid feedback source has been captured
    ESCALATED = "ESCALATED"   # 72h passed with no feedback; hiring manager notified (still monitored)


class FeedbackSource(str, enum.Enum):
    """Where a piece of interview feedback came from."""

    TEAMS = "TEAMS"               # posted in a domain Microsoft Teams hiring channel
    EMAIL = "EMAIL"               # interviewer's email reply
    FORM = "FORM"                 # human submission via the feedback form (POST /interviews/{id}/feedback)
    AI_ANALYSIS = "AI_ANALYSIS"   # produced by Agent 5 from a recording transcript


class EventType(str, enum.Enum):
    """analytics_events.event_type values (stored as varchar)."""

    CANDIDATE_ADDED = "CANDIDATE_ADDED"
    SKILLS_CONFIRMED = "SKILLS_CONFIRMED"
    SCORE_COMPUTED = "SCORE_COMPUTED"
    CALL_COMPLETED = "CALL_COMPLETED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    FEEDBACK_REQUESTED = "FEEDBACK_REQUESTED"
    FEEDBACK_RECEIVED = "FEEDBACK_RECEIVED"
    FEEDBACK_SUBMITTED = "FEEDBACK_SUBMITTED"
    FEEDBACK_REMINDER_SENT = "FEEDBACK_REMINDER_SENT"
    FEEDBACK_ESCALATED = "FEEDBACK_ESCALATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    BLACKLISTED = "BLACKLISTED"


# ---- Shared SQLAlchemy ENUM type instances ----
# Enums reused across multiple tables MUST share one type object so the
# Postgres `CREATE TYPE` is emitted exactly once during create_all.
from sqlalchemy import Enum as _SAEnum  # noqa: E402

work_mode_enum = _SAEnum(WorkMode, name="work_mode")
shift_preference_enum = _SAEnum(ShiftPreference, name="shift_preference")
application_status_enum = _SAEnum(ApplicationStatus, name="application_status")
# Recommendation is shared by interview_feedback + interview_feedback_messages;
# feedback_source by interview_feedback + interview_feedback_messages.
recommendation_enum = _SAEnum(Recommendation, name="recommendation")
feedback_source_enum = _SAEnum(FeedbackSource, name="feedback_source")
