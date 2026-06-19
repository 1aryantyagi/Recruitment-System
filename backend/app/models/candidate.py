"""Candidate tables: candidates (§9.6), candidate_resumes (§9.7)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col, updated_at_col
from app.models.enums import (
    CandidateSource,
    DetailRequestStatus,
    shift_preference_enum,
    work_mode_enum,
)
from app.models.types import EncryptedInt, EncryptedString


class Candidate(Base):
    __tablename__ = "candidates"

    id = pk_col()
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)  # dedup key (§4.3)
    phone = Column(EncryptedString, nullable=True)  # encrypted at rest (§4.9)
    current_location = Column(String(200), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
    domain_id = fk_col("domains.id", nullable=True, index=True)
    total_experience_years = Column(Float, nullable=True, index=True)
    current_company = Column(String(200), nullable=True)
    current_designation = Column(String(200), nullable=True)
    current_ctc = Column(EncryptedInt, nullable=True)  # encrypted (§4.9)
    expected_ctc = Column(EncryptedInt, nullable=True)  # encrypted (§4.9)
    notice_period_days = Column(Integer, nullable=True, index=True)
    availability_date = Column(Date, nullable=True)
    work_mode_preference = Column(work_mode_enum, nullable=True, index=True)
    shift_preference = Column(shift_preference_enum, nullable=True)
    source = Column(SAEnum(CandidateSource, name="candidate_source"), nullable=False, index=True)
    source_detail = Column(Text, nullable=True)
    uploaded_by = fk_col("users.id", nullable=True)
    custom_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ai_summary = Column(Text, nullable=True)

    # Blacklist (§8.2)
    is_blacklisted = Column(Boolean, nullable=False, default=False, index=True)
    blacklist_reason_id = fk_col("pipeline_status_reasons.id", nullable=True)
    blacklisted_by = fk_col("users.id", nullable=True)
    blacklisted_at = Column(DateTime(timezone=True), nullable=True)
    blacklist_note = Column(Text, nullable=True)

    created_at = created_at_col()
    updated_at = updated_at_col()

    domain = relationship("Domain")
    skills = relationship("CandidateSkill", cascade="all, delete-orphan")
    resumes = relationship("CandidateResume", back_populates="candidate", cascade="all, delete-orphan")
    detail_requests = relationship(
        "CandidateDetailRequest", back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateResume(Base):
    __tablename__ = "candidate_resumes"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    file_url = Column(String(1000), nullable=True)
    redacted_file_url = Column(String(1000), nullable=True)
    parsed_text = Column(Text, nullable=True)
    # Generated tsvector (REQ FTS) — auto-computed from parsed_text.
    search_vector = Column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(parsed_text, ''))", persisted=True),
    )
    gmail_message_id = Column(String(200), nullable=True)  # idempotency for Gmail intake (§4.3)
    is_latest = Column(Boolean, nullable=False, default=True)
    uploaded_by = fk_col("users.id", nullable=True)
    uploaded_at = created_at_col()

    candidate = relationship("Candidate", back_populates="resumes")

    __table_args__ = (
        Index("ix_resume_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "uq_resume_gmail_message_id",
            "gmail_message_id",
            unique=True,
            postgresql_where=text("gmail_message_id IS NOT NULL"),
        ),
    )


class CandidateDetailRequest(Base):
    """Tracks an auto-sent email asking a candidate for the logistics fields that
    their resume omitted (current/expected CTC, notice period, availability, shift
    and work-mode preference), and the parsed reply once it arrives.

    One row per outbound request. The Gmail `thread_id` matches the candidate's
    reply back to its request; `status` walks SENT → RECEIVED (or FAILED)."""

    __tablename__ = "candidate_detail_requests"

    id = pk_col()
    candidate_id = fk_col("candidates.id", index=True)
    gmail_thread_id = Column(String(200), nullable=True, index=True)  # match the reply
    original_message_id = Column(String(998), nullable=True)  # RFC822 Message-ID for In-Reply-To
    sent_message_id = Column(String(200), nullable=True)  # id of the email we sent
    requested_fields = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status = Column(
        SAEnum(DetailRequestStatus, name="detail_request_status"),
        nullable=False,
        default=DetailRequestStatus.SENT,
        index=True,
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    reply_raw_text = Column(Text, nullable=True)
    parsed_values = Column(JSONB, nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    candidate = relationship("Candidate", back_populates="detail_requests")
