"""Automated interview-feedback collection tables.

Three tables power the post-interview feedback workflow (Teams + email):

  • ``domain_teams_mappings`` — admin-maintained mapping from a hiring ``domain``
    to its Microsoft Teams group/channel, plus the incremental poll cursor.
  • ``interview_feedback_requests`` — one row per interview's feedback cycle: the
    monitoring state (AWAITING → RECEIVED / ESCALATED), the email thread used to
    request + remind, and the reminder counter (the "email tracking" record).
  • ``interview_feedback_messages`` — append-only log of *every* collected
    feedback message across sources (the first valid one wins and becomes the
    canonical ``interview_feedback``; later ones are stored as additional).

Mirrors the ``candidate_detail_requests`` precedent (thread-id matching, status
lifecycle) and the ``candidate_resumes.gmail_message_id`` idempotency index.
"""
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
    FeedbackRequestStatus,
    feedback_source_enum,
    recommendation_enum,
)


class DomainTeamsMapping(Base):
    """Maps a hiring ``domain`` (AI/ML, Backend, …) to its Microsoft Teams group
    and channel. The feedback monitor uses ``candidate.domain_id`` to pick the
    channel to scan. ``last_synced_at`` is the incremental cursor (only messages
    newer than this are processed)."""

    __tablename__ = "domain_teams_mappings"

    id = pk_col()
    domain_id = fk_col("domains.id", unique=True)  # one Teams group per domain
    teams_group_name = Column(String(200), nullable=False)
    teams_team_id = Column(String(200), nullable=False)
    teams_channel_id = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    domain = relationship("Domain")


class InterviewFeedbackRequest(Base):
    """One feedback cycle per interview. Created when the interview is detected as
    concluded; tracks the email thread used to request/remind, the reminder count,
    and the AWAITING → RECEIVED / ESCALATED lifecycle. ``awaiting_since`` is the
    basis for the 24h / 48h / 72h reminder + escalation math."""

    __tablename__ = "interview_feedback_requests"

    id = pk_col()
    interview_id = fk_col("interviews.id", unique=True, index=True)
    status = Column(
        SAEnum(FeedbackRequestStatus, name="feedback_request_status"),
        nullable=False,
        default=FeedbackRequestStatus.AWAITING,
        index=True,
    )
    source = Column(feedback_source_enum, nullable=True)  # which source won
    # Email thread used to request feedback + match the interviewer's reply.
    gmail_thread_id = Column(String(200), nullable=True, index=True)
    original_message_id = Column(String(998), nullable=True)  # RFC822 Message-ID for In-Reply-To
    sent_message_id = Column(String(200), nullable=True)  # id of the request email we sent
    reminder_count = Column(Integer, nullable=False, default=0)
    awaiting_since = Column(DateTime(timezone=True), nullable=True)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    interview = relationship("Interview")


class InterviewFeedbackMessage(Base):
    """Append-only record of a single collected feedback message (any source).
    ``is_primary`` marks the first/winning one. ``source_message_id`` (the Teams
    message id / Gmail message id) is uniquely indexed so re-polling never
    double-ingests the same message."""

    __tablename__ = "interview_feedback_messages"

    id = pk_col()
    interview_id = fk_col("interviews.id", index=True)
    source = Column(feedback_source_enum, nullable=False)
    author_name = Column(String(200), nullable=True)
    author_email = Column(String(255), nullable=True)
    raw_feedback = Column(Text, nullable=True)
    recommendation = Column(recommendation_enum, nullable=True)
    summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    extracted = Column(JSONB, nullable=True)  # full LLM extraction output
    source_message_id = Column(String(255), nullable=True)  # Teams/Gmail message id (idempotency)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = created_at_col()

    interview = relationship("Interview")

    __table_args__ = (
        Index(
            "uq_feedback_message_source_id",
            "source_message_id",
            unique=True,
            postgresql_where=text("source_message_id IS NOT NULL"),
        ),
    )
