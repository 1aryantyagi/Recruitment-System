"""Call & interview tables: call_logs (§9.13), interviews (§9.14),
interview_feedback (§9.15)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col, updated_at_col
from app.models.enums import (
    CallStatus,
    InterviewStatus,
    Recommendation,
    RoundType,
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
    recommendation = Column(SAEnum(Recommendation, name="recommendation"), nullable=True)
    is_submitted = Column(Boolean, nullable=False, default=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    last_updated_at = Column(DateTime(timezone=True), nullable=True)

    interview = relationship("Interview", back_populates="feedback")
