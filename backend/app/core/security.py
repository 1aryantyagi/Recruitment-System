"""Security primitives: field encryption (AES-256-GCM) and password hashing.

Implements REQ-DP-9: `phone`, `current_ctc`, `expected_ctc` are encrypted at
rest. Encryption is application-level (the key never lives in the DB), which
gives stronger separation than DB-side pgcrypto.
"""
from __future__ import annotations

import base64
import hashlib
import os

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_BYTES = 12


def _derive_key() -> bytes:
    """Return a 32-byte AES key.

    Prefers the configured ENCRYPTION_KEY (urlsafe-base64 of 32 bytes). Falls
    back to SHA-256 of SECRET_KEY so the app still runs in dev without a
    dedicated key configured.
    """
    raw = settings.encryption_key.strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw)
            if len(key) == 32:
                return key
        except Exception:
            pass
        # Not valid base64-32; hash whatever was provided to 32 bytes.
        return hashlib.sha256(raw.encode()).digest()
    return hashlib.sha256(settings.secret_key.encode()).digest()


_KEY = _derive_key()


def encrypt_value(plaintext: str | None) -> str | None:
    """Encrypt a string -> urlsafe-base64(nonce || ciphertext+tag). None passes through."""
    if plaintext is None:
        return None
    aes = AESGCM(_KEY)
    nonce = os.urandom(_NONCE_BYTES)
    ct = aes.encrypt(nonce, str(plaintext).encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt_value(token: str | None) -> str | None:
    """Decrypt a token produced by `encrypt_value`. Returns the raw token on
    failure (e.g. legacy/plain values) so reads never crash."""
    if token is None:
        return None
    try:
        blob = base64.urlsafe_b64decode(token.encode("utf-8"))
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        aes = AESGCM(_KEY)
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return token


# ---------------- Password hashing ----------------

def hash_password(password: str) -> str:
    # bcrypt has a 72-byte input limit; encode + truncate defensively.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False
