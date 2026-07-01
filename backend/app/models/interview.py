"""Call & interview tables: call_logs (§9.13), interviews (§9.14),
interview_feedback (§9.15)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col, updated_at_col
from app.models.enums import (
    CallStatus,
    InterviewStatus,
    RoundType,
    feedback_source_enum,
    recommendation_enum,
)


class CallLog(Base):
    __tablename__ = "call_logs"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    requisition_id = fk_col("requisitions.id", nullable=True, index=True)
    initiated_by = fk_col("users.id", nullable=True)
    twilio_call_sid = Column(String(100), nullable=True, unique=True)
    status = Column(SAEnum(CallStatus, name="call_status"), nullable=False, default=CallStatus.INITIATED)
    recording_url = Column(String(1000), nullable=True)
    transcript = Column(Text, nullable=True)
    screening_answers = Column(JSONB, nullable=True)  # [{question, answer, ai_comment, ai_rating}]
    ai_score = Column(Float, nullable=True)  # 0-1 overall screening score
    # The live (in-call) qualification judgement from the Realtime voice agent.
    # NULL = not decided live (legacy/IVR calls); the post-call evaluation treats
    # an explicit False as authoritative and suppresses the auto-SHORTLIST.
    qualified = Column(Boolean, nullable=True)
    question_set = Column(JSONB, nullable=True)  # questions asked
    duration_seconds = Column(Integer, nullable=True)
    called_at = created_at_col()
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Interview(Base):
    __tablename__ = "interviews"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    requisition_id = fk_col("requisitions.id", nullable=True, index=True)
    interviewer_id = fk_col("users.id", nullable=True)
    round_number = Column(Integer, nullable=False, default=1)
    round_type = Column(SAEnum(RoundType, name="round_type"), nullable=False)
    status = Column(SAEnum(InterviewStatus, name="interview_status"), nullable=False, default=InterviewStatus.SCHEDULED)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    meeting_link = Column(String(500), nullable=True)
    calendar_event_id = Column(String(200), nullable=True)
    # Whether the candidate's calendar invite email was actually sent. False after
    # scheduling means the interview exists but no invite went out (e.g. Gmail not
    # configured, send failed, or the candidate has no real email) — surfaced to HR.
    invite_sent = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    recording_url = Column(String(1000), nullable=True)
    transcript = Column(Text, nullable=True)
    ai_analysis = Column(JSONB, nullable=True)
    ai_overall_rating = Column(Float, nullable=True)  # 0.0-1.0
    analysis_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = fk_col("users.id", nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    interviewer = relationship("User", foreign_keys=[interviewer_id])
    feedback = relationship("InterviewFeedback", back_populates="interview", uselist=False, cascade="all, delete-orphan")

    # DB-level defense against double-booking one interviewer at the same instant
    # (the slot engine also re-checks in app code). Partial: only live rounds with
    # a concrete interviewer + time can collide.
    __table_args__ = (
        Index(
            "uq_interview_slot_per_interviewer",
            "interviewer_id",
            "scheduled_at",
            unique=True,
            postgresql_where=text(
                "status IN ('SCHEDULED','RESCHEDULED') "
                "AND scheduled_at IS NOT NULL AND interviewer_id IS NOT NULL"
            ),
        ),
    )


class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"

    id = pk_col()
    interview_id = fk_col("interviews.id", index=True)
    submitted_by = fk_col("users.id", nullable=True)
    # AI-produced (from Agent 5)
    ai_summary = Column(Text, nullable=True)
    ai_strengths = Column(Text, nullable=True)
    ai_concerns = Column(Text, nullable=True)
    ai_qa_breakdown = Column(JSONB, nullable=True)
    # Human
    human_summary = Column(Text, nullable=True)
    human_strengths = Column(Text, nullable=True)
    human_concerns = Column(Text, nullable=True)
    technical_rating = Column(Integer, nullable=True)
    communication_rating = Column(Integer, nullable=True)
    problem_solving_rating = Column(Integer, nullable=True)
    culture_fit_rating = Column(Integer, nullable=True)
    overall_rating = Column(Integer, nullable=True)
    recommendation = Column(recommendation_enum, nullable=True)
    # Which channel produced the canonical (first-won) feedback: TEAMS | EMAIL | FORM | AI_ANALYSIS.
    source = Column(feedback_source_enum, nullable=True)
    is_submitted = Column(Boolean, nullable=False, default=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    last_updated_at = Column(DateTime(timezone=True), nullable=True)

    interview = relationship("Interview", back_populates="feedback")
