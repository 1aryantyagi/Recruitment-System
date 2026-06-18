"""API integration tests (require local Postgres up + migrated + seeded).

LLM is disabled per-test (monkeypatch) so these run fully offline.
"""
from __future__ import annotations

import time

from tests.conftest import DOCX_MIME, make_docx

RESUME = "Jane Smith\nPython, Docker, PostgreSQL\n5 years experience.\n"


def test_login_and_me(client, hr_headers):
    r = client.get("/auth/me", headers=hr_headers)
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "HR"


def test_bad_password_401(client):
    r = client.post("/auth/login", json={"email": "hr@local.dev", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_missing_token_401(client):
    r = client.get("/candidates")
    assert r.status_code == 401


def test_list_envelope_and_pagination_clamp(client, hr_headers):
    r = client.get("/candidates?limit=999", headers=hr_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("data", "total", "page", "limit", "total_pages"):
        assert key in body
    assert body["limit"] <= 100  # clamped, not rejected


def test_requisitions_seeded(client, hr_headers):
    r = client.get("/requisitions", headers=hr_headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 2


def test_rbac_dm_cannot_upload(client, dm_headers):
    files = [("files", ("x.docx", make_docx(RESUME), DOCX_MIME))]
    r = client.post("/candidates", headers=dm_headers, files=files)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_blacklist_requires_admin_for_listing(client, hr_headers):
    r = client.get("/candidates?blacklisted=true", headers=hr_headers)
    assert r.status_code == 403


def test_upload_dedup(client, hr_headers, monkeypatch):
    # Disable LLM so intake runs offline (stub extraction; email from override).
    monkeypatch.setattr("app.agents.resume_intake.llm.llm_available", lambda: False)
    email = f"jane.{int(time.time()*1000)}@example.com"
    files = [("files", ("jane.docx", make_docx(RESUME), DOCX_MIME))]
    r1 = client.post("/candidates", headers=hr_headers, files=files, data={"email": email, "full_name": "Jane Smith"})
    assert r1.status_code == 200
    res1 = r1.json()["data"]["results"][0]
    assert res1.get("candidate_id")

    files = [("files", ("jane2.docx", make_docx(RESUME), DOCX_MIME))]
    r2 = client.post("/candidates", headers=hr_headers, files=files, data={"email": email})
    res2 = r2.json()["data"]["results"][0]
    assert res2.get("error") == "DUPLICATE_CANDIDATE"


def test_skills_grouped(client, hr_headers):
    r = client.get("/skills", headers=hr_headers)
    assert r.status_code == 200
    assert "by_category" in r.json()["data"]


def test_analytics_dashboard(client, hr_headers):
    r = client.get("/analytics/dashboard", headers=hr_headers)
    assert r.status_code == 200
    assert "funnel" in r.json()["data"]
