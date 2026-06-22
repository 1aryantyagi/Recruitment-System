"""Database engine, session factory, and declarative base (the Datagraph core).

A connection pool sized to the worker count keeps DB access bounded under
concurrency (§11). All persistence flows through SQLAlchemy sessions.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings
from app.core.logging import get_logger

log = get_logger("core.db")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    log.debug("core.db.session.open")
    try:
        yield db
    finally:
        db.close()
        log.debug("core.db.session.close")
