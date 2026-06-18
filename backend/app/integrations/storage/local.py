"""Local-disk file storage with short-lived signed URLs.

Stands in for Supabase Storage in local dev. Files live under `backend/storage`;
access is granted only through time-limited signed tokens (mirrors pre-signed
URLs — §5.4). Swappable for Supabase Storage behind the same interface.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import uuid
from pathlib import Path

from jose import JWTError, jwt

from app.config import settings

STORAGE_DIR = Path(__file__).resolve().parents[3] / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

_ALG = "HS256"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(name: str) -> str:
    return _SAFE.sub("_", name)[:120] or "file"


def save_file(content: bytes, filename: str, subdir: str = "resumes") -> str:
    """Persist bytes and return a relative storage key."""
    folder = STORAGE_DIR / subdir
    folder.mkdir(parents=True, exist_ok=True)
    key = f"{subdir}/{uuid.uuid4().hex}_{_safe_name(filename)}"
    (STORAGE_DIR / key).write_bytes(content)
    return key


def read_file(key: str) -> bytes:
    path = (STORAGE_DIR / key).resolve()
    if not str(path).startswith(str(STORAGE_DIR.resolve())):
        raise ValueError("Path traversal detected")
    return path.read_bytes()


def file_exists(key: str) -> bool:
    return (STORAGE_DIR / key).exists()


def signed_url(key: str, expires_in: int = 300) -> str:
    """Return a backend URL with a signed, expiring access token."""
    exp = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)).timestamp())
    token = jwt.encode({"key": key, "exp": exp, "scope": "file"}, settings.secret_key, algorithm=_ALG)
    return f"{settings.backend_base_url}/files/{token}"


def resolve_signed(token: str) -> str:
    """Validate a signed token and return the storage key."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALG])
    except JWTError as exc:
        raise ValueError("Invalid or expired file token") from exc
    if payload.get("scope") != "file":
        raise ValueError("Wrong token scope")
    return payload["key"]
