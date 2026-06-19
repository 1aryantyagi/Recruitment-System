"""Candidate detail-collection tests.

Offline tests (field detection, coercion, fallback template, reply application)
mock the LLM and need neither DB nor network. The DB tests exercise the full
outbound `request_details` + inbound `ingest_detail_reply` round-trip against the
local Postgres (5434), migrated — mirroring `test_gmail_auth.py`.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.agents import detail_collection as dc
from app.integrations.gmail import client as gmail
from app.llm import client as llm
from app.models import AnalyticsEvent, Candidate, CandidateDetailRequest
from app.models.enums import CandidateSource, DetailRequestStatus, ShiftPreference, WorkMode
from app.schemas.llm import CandidateDetailsExtraction


# ---------------- offline: pure helpers ----------------

def test_missing_detail_fields():
    c = Candidate(full_name="A", email="a@x.com", current_ctc=1500000, notice_period_days=30)
    missing = dc.missing_detail_fields(c)
    assert "current_ctc" not in missing and "notice_period_days" not in missing
    assert set(missing) == {
        "expected_ctc", "availability_date", "work_mode_preference", "shift_preference"
    }


def test_missing_detail_fields_all_present():
    c = Candidate(
        full_name="A", email="a@x.com", current_ctc=1, expected_ctc=2, notice_period_days=3,
        availability_date=dt.date(2026, 8, 1),
        work_mode_preference=WorkMode.HYBRID, shift_preference=ShiftPreference.DAY,
    )
    assert dc.missing_detail_fields(c) == []


def test_coercion_helpers():
    assert dc._coerce_int("60") == 60
    assert dc._coerce_int(None) is None
    assert dc._coerce_int("two") is None
    assert dc._coerce_date("2026-08-01") == dt.date(2026, 8, 1)
    assert dc._coerce_date("not-a-date") is None
    assert dc._coerce_date(None) is None
    assert dc._coerce_enum(WorkMode, "hybrid") == WorkMode.HYBRID
    assert dc._coerce_enum(ShiftPreference, "DAY") == ShiftPreference.DAY
    assert dc._coerce_enum(WorkMode, "weekends") is None


def test_apply_extraction_only_fills_missing():
    c = Candidate(full_name="A", email="a@x.com", current_ctc=1500000)  # already has current_ctc
    ext = {
        "current_ctc": 9999999,           # must NOT overwrite existing value
        "expected_ctc": 2000000,
        "notice_period_days": 60,
        "availability_date": "2026-09-15",
        "work_mode_preference": "REMOTE",
        "shift_preference": "FLEXIBLE",
    }
    applied = dc._apply_extraction(c, ext)
    assert "current_ctc" not in applied
    assert c.current_ctc == 1500000  # unchanged
    assert c.expected_ctc == 2000000
    assert c.notice_period_days == 60
    assert c.availability_date == dt.date(2026, 9, 15)
    assert c.work_mode_preference == WorkMode.REMOTE
    assert c.shift_preference == ShiftPreference.FLEXIBLE
    assert set(applied) == {
        "expected_ctc", "notice_period_days", "availability_date",
        "work_mode_preference", "shift_preference",
    }


def test_compose_body_fallback_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: False)
    c = Candidate(full_name="Jordan Lee", email="j@x.com")
    body = dc._compose_body(c, ["current_ctc", "expected_ctc"], requisition_title="Backend Engineer")
    assert "Jordan" in body
    assert "Backend Engineer" in body
    assert dc._FIELD_LABELS["current_ctc"] in body
    assert dc._FIELD_LABELS["expected_ctc"] in body


# ---------------- DB round-trip (require Postgres + migration) ----------------

@pytest.fixture
def db_session():
    from app.database.base import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _make_candidate(db, **kw) -> Candidate:
    c = Candidate(
        full_name=kw.pop("full_name", "Test Candidate"),
        email=kw.pop("email", f"cand+{uuid.uuid4().hex[:8]}@example.com"),
        source=CandidateSource.GMAIL,
        **kw,
    )
    db.add(c)
    db.flush()
    return c


def _cleanup(db, candidate_id):
    # Persist anything still pending (e.g. analytics events) while the candidate
    # row still exists — the session uses autoflush=False, so the FK target must
    # be present before we delete it.
    db.commit()
    db.query(AnalyticsEvent).filter_by(candidate_id=candidate_id).delete()
    db.query(CandidateDetailRequest).filter_by(candidate_id=candidate_id).delete()
    db.query(Candidate).filter_by(id=candidate_id).delete()
    db.commit()


def test_request_details_sends_and_records(db_session, monkeypatch):
    sent = {}
    monkeypatch.setattr(gmail, "send_reply", lambda **kw: sent.update(kw) or "sent-msg-1")
    monkeypatch.setattr(llm, "llm_available", lambda: False)  # use deterministic body
    c = _make_candidate(db_session)
    db_session.commit()
    try:
        row = dc.request_details(
            candidate_id=str(c.id), to_email="applicant@example.com",
            thread_id="thread-1", original_message_id="<orig@mail>", subject="My application",
            db=db_session,
        )
        assert row is not None
        assert row.status == DetailRequestStatus.SENT
        assert row.gmail_thread_id == "thread-1"
        assert row.sent_message_id == "sent-msg-1"
        assert set(row.requested_fields) == set(dc.DETAIL_FIELDS)  # nothing on the resume
        assert sent["to"] == "applicant@example.com"
        assert sent["thread_id"] == "thread-1"
        assert sent["in_reply_to"] == "<orig@mail>"
        assert sent["subject"].startswith("Re: ")
    finally:
        _cleanup(db_session, c.id)


def test_request_details_idempotent(db_session, monkeypatch):
    calls = {"n": 0}

    def _send(**kw):
        calls["n"] += 1
        return f"msg-{calls['n']}"

    monkeypatch.setattr(gmail, "send_reply", _send)
    monkeypatch.setattr(llm, "llm_available", lambda: False)
    c = _make_candidate(db_session)
    db_session.commit()
    try:
        first = dc.request_details(candidate_id=str(c.id), to_email="a@example.com",
                                   thread_id="t", db=db_session)
        second = dc.request_details(candidate_id=str(c.id), to_email="a@example.com",
                                    thread_id="t", db=db_session)
        assert first is not None and second is None  # second skipped
        assert calls["n"] == 1  # only one email sent
    finally:
        _cleanup(db_session, c.id)


def test_request_details_skips_when_nothing_missing(db_session, monkeypatch):
    monkeypatch.setattr(gmail, "send_reply", lambda **kw: pytest.fail("should not send"))
    c = _make_candidate(
        db_session, current_ctc=1, expected_ctc=2, notice_period_days=3,
        availability_date=dt.date(2026, 8, 1),
        work_mode_preference=WorkMode.ONSITE, shift_preference=ShiftPreference.DAY,
    )
    db_session.commit()
    try:
        assert dc.request_details(candidate_id=str(c.id), to_email="a@example.com", db=db_session) is None
    finally:
        _cleanup(db_session, c.id)


def test_request_details_skips_placeholder_email(db_session, monkeypatch):
    monkeypatch.setattr(gmail, "send_reply", lambda **kw: pytest.fail("should not send"))
    c = _make_candidate(db_session)
    db_session.commit()
    try:
        assert dc.request_details(
            candidate_id=str(c.id), to_email="unknown+abc123@placeholder.local", db=db_session,
        ) is None
        assert dc.request_details(candidate_id=str(c.id), to_email="", db=db_session) is None
    finally:
        _cleanup(db_session, c.id)


def test_ingest_detail_reply_parses_and_applies(db_session, monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(
        llm, "complete_structured",
        lambda *a, **k: CandidateDetailsExtraction(
            current_ctc=1500000, expected_ctc=2000000, notice_period_days=60,
            availability_date="2026-09-01", work_mode_preference="HYBRID",
            shift_preference="DAY",
        ),
    )
    c = _make_candidate(db_session)
    req = CandidateDetailRequest(
        candidate_id=c.id, gmail_thread_id="t", status=DetailRequestStatus.SENT,
        requested_fields=dc.DETAIL_FIELDS,
    )
    db_session.add(req)
    db_session.flush()
    db_session.commit()
    try:
        applied = dc.ingest_detail_reply(request=req, reply_text="My CTC is 15 LPA...", db=db_session)
        db_session.commit()
        db_session.refresh(c)
        db_session.refresh(req)
        assert req.status == DetailRequestStatus.RECEIVED
        assert req.received_at is not None
        assert c.current_ctc == 1500000 and c.expected_ctc == 2000000
        assert c.notice_period_days == 60
        assert c.availability_date == dt.date(2026, 9, 1)
        assert c.work_mode_preference == WorkMode.HYBRID
        assert c.shift_preference == ShiftPreference.DAY
        assert set(applied) == set(dc.DETAIL_FIELDS)
    finally:
        _cleanup(db_session, c.id)
