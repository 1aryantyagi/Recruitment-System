"""Gmail durable-auth tests.

Offline tests (resolver precedence, no-op, backoff, OAuth state) mock Google and
need neither DB nor network. The endpoint/DB tests use the shared `client`/
`admin_headers` fixtures and require local Postgres (5434), migrated.
"""
from __future__ import annotations

import datetime as dt

import pytest
from google.auth.exceptions import RefreshError
from jose import jwt

from app.config import settings
from app.core.auth import ALGORITHM
from app.core.errors import AuthenticationError
from app.integrations.gmail import client as gmail
from app.integrations.gmail import oauth

_PROVIDER = "gmail"


# ---------------- helpers ----------------

class FakeRow:
    """Stand-in for an IntegrationCredential row (offline resolver tests)."""

    def __init__(self, **kw):
        self.provider = _PROVIDER
        self.disabled = False
        self.refresh_token = None
        self.access_token = None
        self.token_expiry = None
        self.connected_email = None
        self.scopes = None
        self.last_error = None
        self.last_synced_at = None
        for k, v in kw.items():
            setattr(self, k, v)


class FakeCreds:
    def __init__(self, *, refresh_raises=False, rotate_to=None):
        self.valid = False
        self.token = None
        self.expiry = None
        self.refresh_token = "rt-original"
        self._refresh_raises = refresh_raises
        self._rotate_to = rotate_to

    def refresh(self, _request):
        if self._refresh_raises:
            raise RefreshError("invalid_grant: Token has been expired or revoked.")
        self.token = "new-access-token"
        self.expiry = dt.datetime(2099, 1, 1, 0, 0, 0)  # naive UTC, as google sets it
        if self._rotate_to is not None:
            self.refresh_token = self._rotate_to
        self.valid = True


@pytest.fixture(autouse=True)
def _reset_gmail_state():
    gmail.clear_cache()
    yield
    gmail.clear_cache()


def _unconfigure_env(monkeypatch):
    monkeypatch.setattr(settings, "google_service_account_json", "")
    monkeypatch.setattr(settings, "gmail_impersonate_email", "")
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")


# ---------------- offline: resolver precedence ----------------

def test_resolver_precedence_service_account(monkeypatch):
    monkeypatch.setattr(settings, "google_service_account_json", '{"type": "service_account"}')
    monkeypatch.setattr(settings, "gmail_impersonate_email", "resumes@company.com")
    monkeypatch.setattr(gmail, "_load_db_row", lambda db=None: FakeRow(refresh_token="rt"))

    from google.oauth2 import service_account

    class FakeSACreds:
        def __init__(self):
            self.subject = None

        def with_subject(self, email):
            self.subject = email
            return self

    monkeypatch.setattr(
        service_account.Credentials, "from_service_account_info",
        lambda info, scopes=None: FakeSACreds(),
    )

    creds, mode = gmail._resolve_credentials()
    assert mode == "service_account"
    assert creds.subject == "resumes@company.com"


def test_resolver_precedence_oauth_db_over_env(monkeypatch):
    monkeypatch.setattr(settings, "google_service_account_json", "")
    monkeypatch.setattr(settings, "gmail_impersonate_email", "")
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_refresh_token", "env-rt")  # legacy present too
    monkeypatch.setattr(gmail, "_load_db_row", lambda db=None: FakeRow(refresh_token="db-rt"))

    creds, mode = gmail._resolve_credentials()
    assert mode == "oauth_db"
    assert creds.refresh_token == "db-rt"  # DB wins over env


def test_resolver_precedence_legacy_env(monkeypatch):
    monkeypatch.setattr(settings, "google_service_account_json", "")
    monkeypatch.setattr(settings, "gmail_impersonate_email", "")
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_refresh_token", "env-rt")
    monkeypatch.setattr(gmail, "_load_db_row", lambda db=None: None)

    creds, mode = gmail._resolve_credentials()
    assert mode == "oauth_env"
    assert creds.refresh_token == "env-rt"


def test_resolver_none_and_noop_when_unconfigured(monkeypatch):
    _unconfigure_env(monkeypatch)
    monkeypatch.setattr(gmail, "_load_db_row", lambda db=None: None)

    assert gmail._resolve_credentials() == (None, None)
    assert gmail.gmail_configured() is False
    assert gmail.current_auth_mode() == "none"
    assert gmail.fetch_unread_resumes() == []  # no-op contract preserved


# ---------------- offline: invalid_grant backoff (env mode, no DB row) ----------------

def test_invalid_grant_triggers_backoff_env(monkeypatch):
    _unconfigure_env(monkeypatch)
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_refresh_token", "env-rt")
    monkeypatch.setattr(gmail, "_load_db_row", lambda db=None: None)

    calls = {"n": 0}

    def _resolve(db=None):
        calls["n"] += 1
        return FakeCreds(refresh_raises=True), "oauth_env"

    monkeypatch.setattr(gmail, "_resolve_credentials", _resolve)

    assert gmail._ensure_credentials() is None
    assert gmail.is_backed_off() is True
    assert gmail._cache == {}  # cache cleared on failure
    assert calls["n"] == 1

    # Backed off → next attempt short-circuits without re-hitting Google.
    assert gmail._ensure_credentials() is None
    assert calls["n"] == 1


# ---------------- offline: OAuth state signing ----------------

def test_state_token_roundtrip():
    state = oauth.mint_state("admin-123")
    payload = oauth.verify_state(state)
    assert payload["purpose"] == "gmail_oauth"
    assert payload["sub"] == "admin-123"


def test_state_token_rejects_tampered_and_wrong_purpose():
    with pytest.raises(AuthenticationError):
        oauth.verify_state(oauth.mint_state("a") + "tamper")

    wrong = jwt.encode({"purpose": "login", "sub": "a"}, settings.secret_key, algorithm=ALGORITHM)
    with pytest.raises(AuthenticationError):
        oauth.verify_state(wrong)


# ---------------- DB / endpoint tests (require Postgres + migration) ----------------

@pytest.fixture
def clean_gmail_row():
    from sqlalchemy import delete

    from app.database.base import SessionLocal
    from app.models.integration import IntegrationCredential

    def _wipe():
        s = SessionLocal()
        try:
            s.execute(delete(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER))
            s.commit()
        finally:
            s.close()

    _wipe()
    yield
    _wipe()


def _insert_row(**kw):
    from app.database.base import SessionLocal
    from app.models.integration import IntegrationCredential

    s = SessionLocal()
    try:
        row = IntegrationCredential(provider=_PROVIDER, **kw)
        s.add(row)
        s.commit()
    finally:
        s.close()


def _load_row():
    from sqlalchemy import select

    from app.database.base import SessionLocal
    from app.models.integration import IntegrationCredential

    s = SessionLocal()
    try:
        return s.execute(
            select(IntegrationCredential).where(IntegrationCredential.provider == _PROVIDER)
        ).scalar_one_or_none()
    finally:
        s.close()


def test_status_endpoint_admin_only(client, hr_headers, admin_headers):
    assert client.get("/integrations/gmail/status").status_code == 401
    assert client.get("/integrations/gmail/status", headers=hr_headers).status_code == 403
    r = client.get("/integrations/gmail/status", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "auth_mode" in data and "configured" in data
    # Never leak token values.
    assert "refresh_token" not in data and "access_token" not in data


def test_connect_returns_authorization_url(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    r = client.get("/integrations/gmail/connect", headers=admin_headers)
    assert r.status_code == 200
    url = r.json()["data"]["authorization_url"]
    assert "prompt=consent" in url
    assert "access_type=offline" in url
    assert "test-client-id" in url
    assert "integrations%2Fgmail%2Fcallback" in url or "integrations/gmail/callback" in url


def test_callback_rejects_bad_state(client):
    r = client.get("/integrations/gmail/callback", params={"code": "x", "state": "garbage"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_callback_missing_params_redirects(client):
    r = client.get("/integrations/gmail/callback", follow_redirects=False)
    assert r.status_code == 302
    assert "gmail=error" in r.headers["location"]


def test_invalid_grant_disables_db_row(client, monkeypatch, clean_gmail_row):
    _insert_row(refresh_token="db-rt", auth_mode="oauth_db")
    # Remove env fallback so gmail_configured reflects only the (soon-disabled) row.
    monkeypatch.setattr(settings, "google_service_account_json", "")
    monkeypatch.setattr(settings, "gmail_impersonate_email", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")
    monkeypatch.setattr(gmail, "_resolve_credentials", lambda db=None: (FakeCreds(refresh_raises=True), "oauth_db"))

    assert gmail._ensure_credentials() is None
    row = _load_row()
    assert row is not None and row.disabled is True
    assert row.last_error and "invalid_grant" in row.last_error
    assert gmail.gmail_configured() is False


def test_rotated_refresh_token_persisted(client, monkeypatch, clean_gmail_row):
    _insert_row(refresh_token="old-rt", auth_mode="oauth_db")
    monkeypatch.setattr(
        gmail, "_resolve_credentials",
        lambda db=None: (FakeCreds(rotate_to="rotated-rt"), "oauth_db"),
    )

    creds = gmail._ensure_credentials()
    assert creds is not None

    row = _load_row()
    assert row.refresh_token == "rotated-rt"   # decrypted via EncryptedString
    assert row.access_token == "new-access-token"
    assert row.token_expiry is not None

    # The raw column must be ciphertext, not the plaintext token.
    from sqlalchemy import text

    from app.database.base import SessionLocal

    s = SessionLocal()
    try:
        raw = s.execute(
            text("SELECT refresh_token FROM integration_credentials WHERE provider = :p"),
            {"p": _PROVIDER},
        ).scalar_one()
    finally:
        s.close()
    assert raw != "rotated-rt"
