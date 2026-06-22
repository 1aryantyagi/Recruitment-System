"""Interviewer slot engine.

Expands each interviewer's recurring weekday slot templates into the bookable
calendar for the allowed window, drops past and already-booked times, and books
a chosen slot via Agent 4 (``schedule_interview``).

Booking window (product rule):
  • Mon–Thu  → today through this Friday.
  • Fri/Sat/Sun → next week's Monday through Friday.
  • Never beyond that.

Slot times are company-local (``settings.company_timezone``); every datetime
returned and stored (``interviews.scheduled_at``) is UTC.

The window/expansion/overlap helpers are pure (no DB) so they are unit-testable
offline; :func:`get_open_slots` and :func:`book_slot` add the DB lookups.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.agents.interview_scheduling import schedule_interview
from app.config import settings
from app.core.errors import BadRequestError
from app.core.logging import get_logger, log_step
from app.models import Interview, InterviewerSlot, RequisitionInterviewer, User
from app.models.enums import InterviewStatus, RoundType

log = get_logger("service.slots")

# Interviews whose time is occupied. (COMPLETED/CANCELLED/NO_SHOW free the slot.)
_ACTIVE_STATUSES = (InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED)
# Assumed length of an already-booked interview when checking overlap (we don't
# store per-interview duration).
_ASSUMED_BOOKED_MINUTES = 60


def company_tz() -> ZoneInfo:
    try:
        tz = ZoneInfo(settings.company_timezone)
        log.debug("slots.company_tz", value=settings.company_timezone)
        return tz
    except Exception:  # bad/unknown tz name → fail safe to UTC
        log.warning("slots.company_tz.bad", value=settings.company_timezone)
        return ZoneInfo("UTC")


@dataclass(frozen=True)
class SlotOption:
    """A concrete, offerable interview slot."""

    interviewer_id: str
    interviewer_name: str
    start_utc: dt.datetime      # tz-aware UTC — what gets stored
    start_local: dt.datetime    # tz-aware company-local — what gets spoken
    duration_minutes: int

    @property
    def label(self) -> str:
        """Human phrasing for the voice agent, e.g. 'Mon 23 Jun, 4:30 PM'."""
        # %-I (no leading zero) is POSIX; fall back to lstrip for portability.
        return self.start_local.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")

    def to_dict(self) -> dict:
        return {
            "interviewer_id": self.interviewer_id,
            "interviewer_name": self.interviewer_name,
            "start_utc": self.start_utc.isoformat(),
            "start_local": self.start_local.isoformat(),
            "label": self.label,
            "duration_minutes": self.duration_minutes,
        }


@dataclass(frozen=True)
class SlotTemplate:
    """A recurring weekday slot, decoupled from the ORM row for pure expansion."""

    interviewer_id: str
    interviewer_name: str
    slot_time: dt.time
    weekday_mask: int
    duration_minutes: int


# ---------------- pure helpers (no DB / no network) ----------------
def compute_booking_window(now_local: dt.datetime) -> tuple[dt.date, dt.date]:
    """Inclusive (start_date, end_date) of bookable weekdays for ``now_local``."""
    today = now_local.date()
    wd = today.weekday()  # Mon=0 … Sun=6
    if wd <= 3:  # Mon–Thu: rest of this week through Friday
        start, end = today, today + dt.timedelta(days=4 - wd)
    else:
        # Fri(4)/Sat(5)/Sun(6): roll to next week's Mon–Fri
        next_monday = today + dt.timedelta(days=7 - wd)
        start, end = next_monday, next_monday + dt.timedelta(days=4)
    log.debug("slots.compute_booking_window", weekday=wd,
              start_date=start.isoformat(), end_date=end.isoformat())
    return start, end


def expand_templates(
    templates: list[SlotTemplate],
    window: tuple[dt.date, dt.date],
    now_local: dt.datetime,
    tz: ZoneInfo,
) -> list[SlotOption]:
    """Expand templates across every in-window weekday they cover, dropping any
    slot at or before ``now_local``. Returned sorted by start time."""
    start_date, end_date = window
    out: list[SlotOption] = []
    day = start_date
    while day <= end_date:
        wd = day.weekday()
        for t in templates:
            if not (t.weekday_mask >> wd) & 1:
                continue
            start_local = dt.datetime.combine(day, t.slot_time, tzinfo=tz)
            if start_local <= now_local:
                continue
            out.append(
                SlotOption(
                    interviewer_id=t.interviewer_id,
                    interviewer_name=t.interviewer_name,
                    start_utc=start_local.astimezone(dt.timezone.utc),
                    start_local=start_local,
                    duration_minutes=t.duration_minutes,
                )
            )
        day += dt.timedelta(days=1)
    out.sort(key=lambda s: s.start_utc)
    log.debug("slots.expand_templates", template_count=len(templates),
              candidate_count=len(out),
              start_date=start_date.isoformat(), end_date=end_date.isoformat())
    return out


def _overlaps(a_start: dt.datetime, a_minutes: int, b_start: dt.datetime, b_minutes: int) -> bool:
    a_end = a_start + dt.timedelta(minutes=a_minutes)
    b_end = b_start + dt.timedelta(minutes=b_minutes)
    return a_start < b_end and b_start < a_end


def filter_booked(
    candidates: list[SlotOption],
    booked: list[tuple[str, dt.datetime]],
) -> list[SlotOption]:
    """Drop candidate slots that overlap an existing booking for the same
    interviewer. ``booked`` is [(interviewer_id, start_utc)]."""
    by_interviewer: dict[str, list[dt.datetime]] = {}
    for iid, start in booked:
        by_interviewer.setdefault(str(iid), []).append(start.astimezone(dt.timezone.utc))
    free: list[SlotOption] = []
    for c in candidates:
        existing = by_interviewer.get(c.interviewer_id, ())
        if any(_overlaps(c.start_utc, c.duration_minutes, b, _ASSUMED_BOOKED_MINUTES) for b in existing):
            continue
        free.append(c)
    log.debug("slots.filter_booked", candidate_count=len(candidates),
              booked_count=len(booked), free_count=len(free))
    return free


# ---------------- DB-backed API ----------------
def get_open_slots(db, *, requisition_id, now: dt.datetime | None = None,
                   limit: int | None = None) -> list[SlotOption]:
    """Open (free) interview slots for a requisition within the allowed window."""
    if not requisition_id:
        return []
    with log_step(log, "slots.get_open", requisition_id=str(requisition_id),
                  limit=limit) as step:
        tz = company_tz()
        now_utc = now or dt.datetime.now(dt.timezone.utc)
        now_local = now_utc.astimezone(tz)
        window = compute_booking_window(now_local)
        log.debug("slots.get_open.window", requisition_id=str(requisition_id),
                  start_date=window[0].isoformat(), end_date=window[1].isoformat())

        rows = db.execute(
            select(InterviewerSlot, User.name)
            .join(RequisitionInterviewer,
                  RequisitionInterviewer.interviewer_id == InterviewerSlot.interviewer_id)
            .join(User, User.id == InterviewerSlot.interviewer_id)
            .where(
                RequisitionInterviewer.requisition_id == uuid.UUID(str(requisition_id)),
                InterviewerSlot.is_active.is_(True),
                User.is_active.is_(True),
            )
        ).all()
        templates = [
            SlotTemplate(str(s.interviewer_id), name, s.slot_time, s.weekday_mask, s.duration_minutes)
            for s, name in rows
        ]
        log.debug("slots.get_open.templates", requisition_id=str(requisition_id),
                  template_count=len(templates))
        candidates = expand_templates(templates, window, now_local, tz)
        log.debug("slots.get_open.expanded", requisition_id=str(requisition_id),
                  candidate_count=len(candidates))
        if not candidates:
            step["free_count"] = 0
            return []

        lo = candidates[0].start_utc - dt.timedelta(minutes=_ASSUMED_BOOKED_MINUTES)
        hi = candidates[-1].start_utc + dt.timedelta(
            minutes=max(c.duration_minutes for c in candidates) + _ASSUMED_BOOKED_MINUTES)
        interviewer_ids = {uuid.UUID(t.interviewer_id) for t in templates}
        booked = db.execute(
            select(Interview.interviewer_id, Interview.scheduled_at).where(
                Interview.status.in_(_ACTIVE_STATUSES),
                Interview.interviewer_id.in_(interviewer_ids),
                Interview.scheduled_at.is_not(None),
                Interview.scheduled_at >= lo,
                Interview.scheduled_at <= hi,
            )
        ).all()
        log.debug("slots.get_open.booked", requisition_id=str(requisition_id),
                  range_lo=lo.isoformat(), range_hi=hi.isoformat(),
                  booked_count=len(booked))
        free = filter_booked(candidates, [(str(iid), sa) for iid, sa in booked])
        result = free[:limit] if limit else free
        step["free_count"] = len(free)
        step["returned_count"] = len(result)
        return result


def book_slot(db, *, candidate_id, requisition_id, interviewer_id, start_utc,
              round_type: RoundType = RoundType.L1, created_by=None) -> dict:
    """Book a previously-offered slot. Re-validates the slot is still open
    (race guard) before delegating to Agent 4. Shares the caller's transaction."""
    with log_step(log, "slots.book", candidate_id=str(candidate_id),
                  requisition_id=str(requisition_id),
                  interviewer_id=str(interviewer_id),
                  round_type=getattr(round_type, "value", str(round_type))) as step:
        start_utc = _ensure_utc(start_utc)
        log.debug("slots.book.ensure_utc", start_utc=start_utc.isoformat())
        open_slots = get_open_slots(db, requisition_id=requisition_id)
        chosen = next(
            (s for s in open_slots
             if s.interviewer_id == str(interviewer_id) and _same_minute(s.start_utc, start_utc)),
            None,
        )
        if chosen is None:
            step["slot_found"] = False
            log.warning("slots.book.race",
                        candidate_id=str(candidate_id),
                        requisition_id=str(requisition_id),
                        interviewer_id=str(interviewer_id),
                        start_utc=start_utc.isoformat(),
                        open_count=len(open_slots))
            raise BadRequestError("That interview slot is no longer available")
        step["slot_found"] = True
        log.info("slots.book.slot_found", interviewer_id=str(interviewer_id),
                 start_utc=chosen.start_utc.isoformat())
        with log_step(log, "slots.book.schedule_interview",
                      candidate_id=str(candidate_id),
                      interviewer_id=str(interviewer_id),
                      scheduled_at=chosen.start_utc.isoformat()) as sched_step:
            result = schedule_interview(
                candidate_id=candidate_id,
                requisition_id=requisition_id,
                interviewer_id=interviewer_id,
                round_type=round_type,
                scheduled_at=chosen.start_utc,
                created_by=created_by,
                db=db,
            )
            sched_step["interview_id"] = str(result.get("interview_id")) if isinstance(result, dict) else None
        return result


def _ensure_utc(value) -> dt.datetime:
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _same_minute(a: dt.datetime, b: dt.datetime) -> bool:
    return a.replace(second=0, microsecond=0) == b.replace(second=0, microsecond=0)
