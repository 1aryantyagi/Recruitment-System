"""Authentication & authorization tests (require local Postgres up + migrated + seeded).

Covers: login success/failure, token validation (missing/invalid/expired),
RBAC, refresh-token rotation + reuse detection + logout revocation, and
resource-ownership (owner-only writes / horizontal-access-control).
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from jose import jwt
from sqlalchemy import select

from app.config import settings
from app.core.auth import ALGORITHM
from app.database.base import SessionLocal
from app.models import Candidate, User
from app.models.enums import CandidateSource
from tests.conftest import _token


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def alice_headers(client):
    """A second HR user (distinct from hr@local.dev) for ownership tests."""
    return {"Authorization": f"Bearer {_token(client, 'alice@local.dev', 'int123')}"}


def _user_id(email: str) -> uuid.UUID:
    db = SessionLocal()
    try:
        return db.execute(select(User).filter_by(email=email)).scalar_one().id
    finally:
        db.close()


def _make_candidate(uploaded_by: uuid.UUID | None) -> str:
    """Insert a candidate row directly with a controlled owner; returns its id."""
    db = SessionLocal()
    try:
        cand = Candidate(
            full_name="Ownership Probe",
            email=f"own.{uuid.uuid4().hex}@example.com",
            source=CandidateSource.OTHER,
            uploaded_by=uploaded_by,
        )
        db.add(cand)
        db.commit()
        return str(cand.id)
    finally:
        db.close()


def _delete_candidate(candidate_id: str) -> None:
    db = SessionLocal()
    try:
        cand = db.get(Candidate, uuid.UUID(candidate_id))
        if cand is not None:
            db.delete(cand)
            db.commit()
    finally:
        db.close()


# ---------- login ----------

def test_login_success_returns_access_and_refresh(client):
    r = client.post("/auth/login", json={"email": "admin@local.dev", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "ADMIN"


def test_login_invalid_password_401(client):
    r = client.post("/auth/login", json={"email": "hr@local.dev", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_unknown_user_401(client):
    r = client.post("/auth/login", json={"email": "ghost@local.dev", "password": "x"})
    assert r.status_code == 401


# ---------- token validation ----------

def test_missing_token_401(client):
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_expired_token_401(client):
    now = dt.datetime.now(dt.timezone.utc)
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "HR",
         "exp": int((now - dt.timedelta(minutes=1)).timestamp())},
        settings.secret_key, algorithm=ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_token_signed_with_wrong_secret_401(client):
    now = dt.datetime.now(dt.timezone.utc)
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "ADMIN",
         "exp": int((now + dt.timedelta(hours=1)).timestamp())},
        "attacker-secret", algorithm=ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


# ---------- RBAC ----------

def test_authorized_access_200(client, hr_headers):
    assert client.get("/candidates", headers=hr_headers).status_code == 200


def test_admin_only_route_forbidden_for_hr_403(client, hr_headers):
    # GET /users is ADMIN-only.
    r = client.get("/users", headers=hr_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_admin_only_route_ok_for_admin_200(client, admin_headers):
    assert client.get("/users", headers=admin_headers).status_code == 200


# ---------- refresh-token rotation ----------

def test_refresh_rotates_and_old_token_dies(client):
    res = client.post("/auth/login", json={"email": "hr@local.dev", "password": "hr123"}).json()["data"]
    old_refresh = res["refresh_token"]

    r = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    new = r.json()["data"]
    assert new["access_token"] and new["refresh_token"] != old_refresh

    # The new access token is usable.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"}).status_code == 200

    # Reusing the old (rotated) refresh token is rejected...
    assert client.post("/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
    # ...and reuse-detection revokes the family, so the rotated one is dead too.
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_refresh_with_garbage_token_401(client):
    assert client.post("/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


def test_logout_revokes_refresh_token(client):
    res = client.post("/auth/login", json={"email": "dm@local.dev", "password": "dm123"}).json()["data"]
    access, refresh = res["access_token"], res["refresh_token"]

    r = client.post("/auth/logout", json={"refresh_token": refresh},
                    headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # The revoked refresh token can no longer be rotated.
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


# ---------- resource ownership (owner-only writes) ----------

def test_owner_can_update_own_candidate_200(client, hr_headers):
    cid = _make_candidate(uploaded_by=_user_id("hr@local.dev"))
    try:
        r = client.patch(f"/candidates/{cid}", headers=hr_headers, json={"current_location": "Pune"})
        assert r.status_code == 200
    finally:
        _delete_candidate(cid)


def test_other_user_cannot_update_candidate_403(client, alice_headers):
    # Owned by hr@local.dev; alice (a different HR) must be blocked.
    cid = _make_candidate(uploaded_by=_user_id("hr@local.dev"))
    try:
        r = client.patch(f"/candidates/{cid}", headers=alice_headers, json={"current_location": "Pune"})
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        _delete_candidate(cid)


def test_admin_overrides_ownership_on_shared_action_200(client, admin_headers):
    # PATCH /candidates is HR-only by existing design, so ADMIN-override is
    # validated on an endpoint where ADMIN is in the role gate: blacklist
    # (require_roles(HR, ADMIN)). ADMIN may act on a candidate owned by an HR.
    cid = _make_candidate(uploaded_by=_user_id("hr@local.dev"))
    try:
        r = client.post(f"/candidates/{cid}/blacklist", headers=admin_headers, json={"note": "audit test"})
        assert r.status_code == 200
    finally:
        _delete_candidate(cid)


def test_non_owner_hr_cannot_blacklist_others_candidate_403(client, alice_headers):
    # The ownership check also guards the blacklist write: a non-owner HR is blocked.
    cid = _make_candidate(uploaded_by=_user_id("hr@local.dev"))
    try:
        r = client.post(f"/candidates/{cid}/blacklist", headers=alice_headers, json={"note": "nope"})
        assert r.status_code == 403
    finally:
        _delete_candidate(cid)


def test_unowned_candidate_editable_by_any_hr_200(client, alice_headers):
    # uploaded_by=NULL (e.g. email-ingested) → shared/org-owned, any HR may edit.
    cid = _make_candidate(uploaded_by=None)
    try:
        r = client.patch(f"/candidates/{cid}", headers=alice_headers, json={"current_location": "Remote"})
        assert r.status_code == 200
    finally:
        _delete_candidate(cid)
