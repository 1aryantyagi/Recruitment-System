"""Offline unit tests — no DB or network required."""
from __future__ import annotations

from app.agents.resume_scoring import _experience, _notice
from app.core.security import decrypt_value, encrypt_value, hash_password, verify_password


def test_encryption_roundtrip():
    for value in ["9876543210", "", "long secret value ✓"]:
        token = encrypt_value(value)
        assert token != value
        assert decrypt_value(token) == value
    assert encrypt_value(None) is None
    assert decrypt_value(None) is None


def test_password_hashing():
    h = hash_password("hr123")
    assert verify_password("hr123", h)
    assert not verify_password("wrong", h)


def test_experience_score_within_range():
    assert _experience(4, 2, 5) == 1.0
    assert _experience(1, 2, 5) < 1.0  # below min
    assert _experience(10, 2, 5) <= 1.0  # above max, mild penalty
    assert _experience(None, None, None) == 1.0


def test_notice_score_monotonic():
    assert _notice(10) == 1.0
    assert _notice(30) >= _notice(60) >= _notice(90)
    assert _notice(None) == 0.6
