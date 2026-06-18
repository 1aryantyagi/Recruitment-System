"""Org-level tables: users (§9.1), domains (§9.2), departments (§9.3)."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Enum as SAEnum, String

from app.database.base import Base
from app.models.common import created_at_col, pk_col, updated_at_col
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = pk_col()
    name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    role = Column(SAEnum(UserRole, name="user_role"), nullable=False)
    # Local-dev auth (Supabase Auth replacement): password hash for dev login.
    password_hash = Column(String(255), nullable=True)
    is_interviewer = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = created_at_col()
    updated_at = updated_at_col()


class Domain(Base):
    __tablename__ = "domains"

    id = pk_col()
    name = Column(String(100), unique=True, nullable=False)
    created_at = created_at_col()


class Department(Base):
    __tablename__ = "departments"

    id = pk_col()
    name = Column(String(100), unique=True, nullable=False)
    created_at = created_at_col()
