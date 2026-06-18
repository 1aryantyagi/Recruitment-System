"""Pytest fixtures. Tests run against the local Postgres (port 5434) — start it
with `docker compose up -d db` and apply migrations + seed first."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _token(client: TestClient, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def hr_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'hr@local.dev', 'hr123')}"}


@pytest.fixture(scope="session")
def dm_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'dm@local.dev', 'dm123')}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'admin@local.dev', 'admin123')}"}


def make_docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
