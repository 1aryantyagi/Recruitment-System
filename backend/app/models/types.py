"""SQLAlchemy column types for transparent at-rest encryption (REQ-DP-9).

Encrypted values are stored as text; encryption happens on write and decryption
on read, transparently to the ORM. Sensitive numeric fields are stored as
encrypted text and re-coerced to int on read.
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator

from app.core.security import decrypt_value, encrypt_value


class EncryptedString(TypeDecorator):
    """Encrypts a string at rest."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)


class EncryptedInt(TypeDecorator):
    """Encrypts an integer at rest (stored as encrypted text)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(str(int(value)))

    def process_result_value(self, value, dialect):
        dec = decrypt_value(value)
        if dec is None or dec == "":
            return None
        try:
            return int(dec)
        except (TypeError, ValueError):
            return None
