"""Interviewer scheduling tables.

Two tables turn bare ``users`` rows (``is_interviewer=True``) into a bookable
interviewer calendar that the screening voice agent can schedule into:

  • ``requisition_interviewers`` — which interviewers serve a given role.
  • ``interviewer_slots`` — each interviewer's recurring weekday availability
    template (e.g. 16:30 & 20:30 on weekdays).

The bookable calendar for a date = an interviewer's slot templates, expanded
across the allowed window, minus any time already taken in ``interviews``. Slot
times are company-local (``settings.company_timezone``); ``interviews.scheduled_at``
is always stored in UTC.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, SmallInteger, Time, UniqueConstraint

from app.database.base import Base
from app.models.common import created_at_col, fk_col, pk_col, updated_at_col

# Weekday bitmask uses ``date.weekday()`` positions: Mon=bit0 … Sun=bit6.
# Default availability is Monday–Friday.
WEEKDAYS_MON_FRI = 0b0011111  # 31


class RequisitionInterviewer(Base):
    """Maps an interviewer (``users.id``) to a requisition they conduct rounds for.
    One requisition can have several interviewers (the candidate's call picks a
    free slot across any of them)."""

    __tablename__ = "requisition_interviewers"

    id = pk_col()
    requisition_id = fk_col("requisitions.id", index=True)
    interviewer_id = fk_col("users.id", index=True)
    created_at = created_at_col()

    __table_args__ = (
        UniqueConstraint("requisition_id", "interviewer_id", name="uq_requisition_interviewer"),
    )


class InterviewerSlot(Base):
    """A recurring availability slot for an interviewer: a local time-of-day that
    repeats on the weekdays set in ``weekday_mask``. Expanded into concrete
    bookable datetimes by the slot engine."""

    __tablename__ = "interviewer_slots"

    id = pk_col()
    interviewer_id = fk_col("users.id", index=True)
    slot_time = Column(Time(timezone=False), nullable=False)  # company-local, e.g. 16:30
    weekday_mask = Column(SmallInteger, nullable=False, default=WEEKDAYS_MON_FRI)
    duration_minutes = Column(Integer, nullable=False, default=60)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        UniqueConstraint("interviewer_id", "slot_time", name="uq_interviewer_slot_time"),
    )
