"""Offline unit tests for the interviewer slot engine — no DB or network.

Exercises the pure pieces: the booking-window rule (incl. the Friday/weekend
rollover), template expansion (weekday mask, past-time drop, ordering), and the
overlap-based booked-slot filter.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.services.interview_slots import (
    SlotOption,
    SlotTemplate,
    compute_booking_window,
    expand_templates,
    filter_booked,
    get_open_slots,
)

IST = ZoneInfo("Asia/Kolkata")

# Anchored, known weekdays in June/July 2026:
MON = dt.date(2026, 6, 22)   # weekday 0
WED = dt.date(2026, 6, 24)   # weekday 2
THU = dt.date(2026, 6, 25)   # weekday 3
FRI = dt.date(2026, 6, 26)   # weekday 4
SAT = dt.date(2026, 6, 27)   # weekday 5
SUN = dt.date(2026, 6, 28)   # weekday 6
NEXT_MON = dt.date(2026, 6, 29)
NEXT_FRI = dt.date(2026, 7, 3)

_MON_FRI = 0b0011111  # 31


def _at(d: dt.date, h: int, m: int = 0) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=IST)


# ---------------- compute_booking_window ----------------
def test_window_midweek_runs_through_friday():
    assert compute_booking_window(_at(MON, 9)) == (MON, FRI)
    assert compute_booking_window(_at(WED, 9)) == (WED, FRI)
    assert compute_booking_window(_at(THU, 23)) == (THU, FRI)


def test_window_friday_and_weekend_roll_to_next_week():
    for day in (FRI, SAT, SUN):
        assert compute_booking_window(_at(day, 12)) == (NEXT_MON, NEXT_FRI)


def test_window_never_exceeds_next_friday():
    _, end = compute_booking_window(_at(SAT, 12))
    assert end == NEXT_FRI
    assert (end - dt.date.today()).days < 14  # sanity: within two weeks


# ---------------- expand_templates ----------------
def _tpl(time_hm, mask=_MON_FRI, name="Alice", iid="i-alice", dur=60):
    h, m = time_hm
    return SlotTemplate(iid, name, dt.time(h, m), mask, dur)


def test_expand_covers_each_weekday_in_window():
    win = compute_booking_window(_at(MON, 9))
    slots = expand_templates([_tpl((16, 30))], win, _at(MON, 9), IST)
    # Mon–Fri, all in the future relative to Mon 09:00 → 5 slots.
    assert len(slots) == 5
    assert {s.start_local.date() for s in slots} == {MON, dt.date(2026, 6, 23), WED, THU, FRI}


def test_expand_drops_past_times_today():
    win = compute_booking_window(_at(MON, 17))  # past the 16:30 slot today
    slots = expand_templates([_tpl((16, 30))], win, _at(MON, 17), IST)
    assert len(slots) == 4  # Mon dropped, Tue–Fri remain
    assert MON not in {s.start_local.date() for s in slots}


def test_expand_respects_weekday_mask():
    tuesday_only = 0b0000010  # bit1 = Tuesday
    win = compute_booking_window(_at(MON, 9))
    slots = expand_templates([_tpl((16, 30), mask=tuesday_only)], win, _at(MON, 9), IST)
    assert len(slots) == 1
    assert slots[0].start_local.date() == dt.date(2026, 6, 23)


def test_expand_sorts_and_converts_to_utc():
    win = compute_booking_window(_at(MON, 9))
    slots = expand_templates([_tpl((20, 30)), _tpl((16, 30))], win, _at(MON, 9), IST)
    assert slots == sorted(slots, key=lambda s: s.start_utc)
    # 16:30 IST == 11:00 UTC (IST is +05:30)
    first = slots[0]
    assert first.start_local.hour == 16 and first.start_local.minute == 30
    assert first.start_utc.hour == 11 and first.start_utc.minute == 0


# ---------------- filter_booked ----------------
def _slot(d: dt.date, h: int, m: int, iid="i-alice", dur=60) -> SlotOption:
    local = _at(d, h, m)
    return SlotOption(iid, "Alice", local.astimezone(dt.timezone.utc), local, dur)


def test_filter_booked_removes_exact_and_overlapping():
    s_1630 = _slot(WED, 16, 30)
    s_2030 = _slot(WED, 20, 30)
    cands = [s_1630, s_2030]
    # An existing interview at 16:45 overlaps 16:30 but not 20:30.
    booked = [("i-alice", _at(WED, 16, 45).astimezone(dt.timezone.utc))]
    free = filter_booked(cands, booked)
    assert s_1630 not in free
    assert s_2030 in free


def test_filter_booked_keeps_non_overlapping_and_other_interviewers():
    s = _slot(WED, 16, 30, iid="i-alice")
    booked = [
        ("i-alice", _at(WED, 18, 0).astimezone(dt.timezone.utc)),   # 90 min later → no overlap
        ("i-bob", _at(WED, 16, 30).astimezone(dt.timezone.utc)),    # different interviewer
    ]
    assert filter_booked([s], booked) == [s]


# ---------------- label + early return ----------------
def test_slot_label_is_human_readable():
    label = _slot(MON, 16, 30).label
    assert "22 Jun" in label
    assert "4:30 PM" in label


def test_get_open_slots_no_requisition_returns_empty_without_db():
    assert get_open_slots(None, requisition_id=None) == []
