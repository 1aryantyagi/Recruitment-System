"""Shared column factories for the ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID


def pk_col():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk_col(target: str, nullable: bool = False, **kw):
    return Column(UUID(as_uuid=True), ForeignKey(target, ondelete="SET NULL" if nullable else "CASCADE"), nullable=nullable, **kw)


def created_at_col():
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_col():
    return Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
