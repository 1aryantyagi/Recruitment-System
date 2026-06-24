"""DB-backed tests for interviewer scheduling: admin endpoints + the slot engine
booking/double-book guard. Requires the seeded local Postgres (see conftest)."""
from __future__ import annotations

import uuid

import pytest

from app.database.base import SessionLocal
from app.models import Candidate
from app.models.enums import CandidateSource


def _ai_requisition_id(client, headers) -> str:
    r = client.get("/requisitions", headers=headers, params={"limit": 100})
    assert r.status_code == 200, r.text
    for req in r.json()["data"]:
        if req["title"] == "Associate AI Engineer":
            return req["id"]
    pytest.skip("seed requisition 'Associate AI Engineer' not found")


def test_requisition_open_slots_nonempty(client, hr_headers):
    req_id = _ai_requisition_id(client, hr_headers)
    r = client.get(f"/requisitions/{req_id}/open-slots", headers=hr_headers)
    assert r.status_code == 200, r.text
    slots = r.json()["data"]
    assert len(slots) > 0
    s = slots[0]
    assert {"interviewer_id", "start_utc", "label", "duration_minutes"} <= set(s)


def test_requisition_interviewers_seeded(client, hr_headers):
    req_id = _ai_requisition_id(client, hr_headers)
    r = client.get(f"/requisitions/{req_id}/interviewers", headers=hr_headers)
    assert r.status_code == 200, r.text
    names = {ri["interviewer"]["name"] for ri in r.json()["data"]}
    assert "Alice Interviewer" in names and "Bob Interviewer" in names


def test_interviewer_slot_crud(client, admin_headers, hr_headers):
    interviewers = client.get("/interviewers", headers=hr_headers).json()["data"]
    iid = next(i["id"] for i in interviewers if i["name"] == "Bob Interviewer")

    created = client.post(f"/interviewers/{iid}/slots", headers=admin_headers,
                          json={"slot_time": "14:15", "weekday_mask": 0b0011111, "duration_minutes": 45})
    assert created.status_code == 200, created.text
    slot = created.json()["data"]
    assert slot["slot_time"] == "14:15" and slot["duration_minutes"] == 45

    # Toggle inactive, then delete.
    patched = client.patch(f"/interviewers/{iid}/slots/{slot['id']}", headers=admin_headers,
                           json={"is_active": False})
    assert patched.status_code == 200 and patched.json()["data"]["is_active"] is False
    deleted = client.delete(f"/interviewers/{iid}/slots/{slot['id']}", headers=admin_headers)
    assert deleted.status_code == 200


def test_slot_crud_requires_admin(client, hr_headers):
    interviewers = client.get("/interviewers", headers=hr_headers).json()["data"]
    iid = interviewers[0]["id"]
    r = client.post(f"/interviewers/{iid}/slots", headers=hr_headers,
                    json={"slot_time": "11:00"})
    assert r.status_code == 403


def test_open_slots_labels_name_the_interviewer():
    """get_open_slots labels include the interviewer name (so the agent speaks it)."""
    from app.models import Requisition
    from app.services.interview_slots import get_open_slots
    from sqlalchemy import select

    db = SessionLocal()
    try:
        req = db.execute(select(Requisition).filter_by(title="Associate AI Engineer")).scalar_one()
        slots = get_open_slots(db, requisition_id=req.id)
        if not slots:
            pytest.skip("no open slots in the current window")
        assert all(" with " in s.label for s in slots)
    finally:
        db.close()


def test_real_freebusy_drops_clashing_slot_and_fails_open(monkeypatch):
    """A real busy block on the interviewer's calendar drops the overlapping slot;
    an empty/failed Graph response fails open (slots unchanged)."""
    import datetime as dt

    import app.integrations.ms_graph.client as ms_graph
    from app.models import Requisition, User
    from app.services.interview_slots import get_open_slots
    from sqlalchemy import select

    db = SessionLocal()
    try:
        req = db.execute(select(Requisition).filter_by(title="Associate AI Engineer")).scalar_one()
        # Baseline with a guaranteed-empty Graph response (fail-open path).
        monkeypatch.setattr(ms_graph, "get_availability", lambda *a, **k: {})
        baseline = get_open_slots(db, requisition_id=req.id)
        if not baseline:
            pytest.skip("no open slots in the current window")
        target = baseline[0]
        email = db.get(User, uuid.UUID(target.interviewer_id)).email

        # Now report that interviewer busy over the target slot → it must drop.
        def _busy(emails, start_iso, end_iso):
            s = target.start_utc.strftime("%Y-%m-%dT%H:%M:%S")
            e = (target.start_utc + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
            return {"value": [{
                "scheduleId": email,
                "scheduleItems": [{
                    "status": "busy",
                    "start": {"dateTime": s, "timeZone": "UTC"},
                    "end": {"dateTime": e, "timeZone": "UTC"},
                }],
            }]}

        monkeypatch.setattr(ms_graph, "get_availability", _busy)
        after = get_open_slots(db, requisition_id=req.id)
        assert not any(s.interviewer_id == target.interviewer_id and s.start_utc == target.start_utc
                       for s in after)
        # Fail-open: empty response leaves the target slot offerable again.
        monkeypatch.setattr(ms_graph, "get_availability", lambda *a, **k: {})
        assert any(s.interviewer_id == target.interviewer_id and s.start_utc == target.start_utc
                   for s in get_open_slots(db, requisition_id=req.id))
    finally:
        db.close()


def test_infer_requisition_id_from_active_application():
    """A screening call with no requisition infers it from the candidate's active
    application; a candidate with none yields None."""
    from app.agents.telephonic_screening import _infer_requisition_id
    from app.models import JobApplication, Requisition
    from app.models.enums import ApplicationStatus
    from sqlalchemy import select

    db = SessionLocal()
    try:
        req = db.execute(select(Requisition).filter_by(title="Associate AI Engineer")).scalar_one()
        cand = Candidate(full_name="Infer Test", email=f"infer-{uuid.uuid4().hex}@test.local",
                         source=CandidateSource.OTHER)
        db.add(cand)
        db.flush()

        assert _infer_requisition_id(db, str(cand.id)) is None  # no application yet

        db.add(JobApplication(candidate_id=cand.id, requisition_id=req.id,
                              status=ApplicationStatus.SCREENING))
        db.flush()
        assert _infer_requisition_id(db, str(cand.id)) == str(req.id)
    finally:
        db.rollback()
        db.close()


def test_book_slot_and_reject_double_booking():
    """Service-level: booking an open slot succeeds; re-booking the same slot is
    rejected. Runs in a transaction that is rolled back to avoid polluting seed."""
    from app.core.errors import BadRequestError
    from app.models import Requisition
    from app.services.interview_slots import book_slot, get_open_slots
    from sqlalchemy import select

    db = SessionLocal()
    try:
        req = db.execute(select(Requisition).filter_by(title="Associate AI Engineer")).scalar_one()
        slots = get_open_slots(db, requisition_id=req.id)
        if not slots:
            pytest.skip("no open slots in the current window")
        slot = slots[0]

        cand = Candidate(full_name="Slot Test", email=f"slot-{uuid.uuid4().hex}@test.local",
                         source=CandidateSource.OTHER)
        db.add(cand)
        db.flush()

        result = book_slot(db, candidate_id=cand.id, requisition_id=req.id,
                           interviewer_id=slot.interviewer_id, start_utc=slot.start_utc)
        assert result.get("interview_id")

        # The slot is now taken → no longer offered, and re-booking is rejected.
        remaining = get_open_slots(db, requisition_id=req.id)
        assert not any(s.interviewer_id == slot.interviewer_id and s.start_utc == slot.start_utc
                       for s in remaining)
        with pytest.raises(BadRequestError):
            book_slot(db, candidate_id=cand.id, requisition_id=req.id,
                      interviewer_id=slot.interviewer_id, start_utc=slot.start_utc)
    finally:
        db.rollback()
        db.close()
