"""Structured logging via structlog (NFR: Observability)."""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.app_env == "development"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "app"):
    configure_logging()
    return structlog.get_logger(name)
