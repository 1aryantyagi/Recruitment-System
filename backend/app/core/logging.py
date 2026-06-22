"""Structured logging via structlog (NFR: Observability).

structlog events are routed through the stdlib ``logging`` system so the SAME
event reaches multiple handlers at once:

  - stdout  : pretty (development) / JSON (staging+production)  -- console
  - app.log : always JSON, size-rotating                        -- persistent

The bound-logger API is unchanged (``get_logger(name).info("event", k=v)``),
so all existing call sites keep working without edits. This module also exposes
two step-tracing helpers used throughout the codebase:

  - ``log_step``  : a context manager that logs ``<step>.start`` / ``<step>.end``
                    (with ``duration_ms``) or ``<step>.error`` on failure.
  - ``traced``    : a decorator wrapping a sync OR async function in ``log_step``.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import logging.handlers
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import structlog

from app.config import settings

_configured = False

_REDACTED = "***REDACTED***"

# Keys whose VALUES must never be written verbatim (case-insensitive substring
# match). Secrets only -- candidate PII (phone/email/ctc) and transcripts are
# intentionally kept for traceability.
_REDACT_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "encryption_key",
    "jwt",
    "credential",
)


def _redact_processor(_logger: Any, _method: str, event_dict: dict) -> dict:
    """Mask values for keys that look like a secret/token/password.

    Convention for the rest of the codebase: never interpolate a secret into the
    event *name* (this processor can only mask keyword values, not free text).
    """
    for key in list(event_dict.keys()):
        lk = key.lower()
        if any(sub in lk for sub in _REDACT_SUBSTRINGS):
            if event_dict[key] not in (None, ""):
                event_dict[key] = _REDACTED
    return event_dict


# Processors shared by structlog-origin records. The renderer is deliberately
# NOT in this chain: ``ProcessorFormatter`` (attached to each handler) renders,
# so the chain ends with ``wrap_for_formatter`` which hands the formatter an
# unrendered event_dict. Putting a renderer here too would double-render.
_SHARED_PROCESSORS: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    _redact_processor,
]


def _level() -> int:
    return getattr(logging, settings.log_level.upper(), logging.DEBUG)


def _build_formatter(json_mode: bool) -> structlog.stdlib.ProcessorFormatter:
    """Build a ProcessorFormatter for a handler.

    ``foreign_pre_chain`` runs on records that did NOT originate from structlog
    (uvicorn, SQLAlchemy, library tracebacks) so they render through the same
    pipeline (level/timestamp/redaction) instead of crashing the formatter.
    """
    renderer = (
        structlog.processors.JSONRenderer()
        if json_mode
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            _redact_processor,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    log_path = Path(settings.log_file)
    if not log_path.is_absolute():
        log_path = Path(settings.log_dir) / log_path
    # Create the log dir on startup so the file handler never fails on a missing
    # folder (covers both local <backend>/logs and Docker /app/logs).
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # structlog -> stdlib: each event becomes a stdlib LogRecord, formatted by
    # the handler's ProcessorFormatter. Level filtering lives on the root logger
    # and handlers (one source of truth), so we use a non-filtering wrapper here.
    structlog.configure(
        processors=_SHARED_PROCESSORS
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    json_console = settings.app_env != "development"

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(_build_formatter(json_mode=json_console))
    stream_handler.setLevel(_level())

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(_build_formatter(json_mode=True))  # file is ALWAYS JSON
    file_handler.setLevel(_level())

    root = logging.getLogger()
    root.setLevel(_level())

    # Idempotency / --reload safety: drop any handlers we previously added (and
    # basicConfig's default StreamHandler) before re-adding exactly our two, so
    # logs are never emitted twice.
    for h in list(root.handlers):
        if getattr(h, "_app_log_handler", False) or isinstance(h, logging.StreamHandler):
            root.removeHandler(h)
    for h in (stream_handler, file_handler):
        h._app_log_handler = True  # type: ignore[attr-defined]
        root.addHandler(h)

    # Route uvicorn's own loggers through root so their lines are formatted the
    # same way and also land in app.log (instead of their own raw handlers).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True


def get_logger(name: str = "app"):
    configure_logging()
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Step-tracing helpers
# ---------------------------------------------------------------------------
@contextmanager
def log_step(logger: Any, step_name: str, **context: Any) -> Iterator[dict]:
    """Trace a discrete step.

    Logs ``<step>.start`` (+context), then ``<step>.end`` with ``duration_ms`` on
    success, or ``<step>.error`` with the exception + ``duration_ms`` on failure
    (and re-raises). Yields a mutable dict; fields added to it are emitted on
    ``.end``::

        with log_step(log, "score_resume", candidate_id=cid) as step:
            step["score"] = result.score
    """
    logger.info(f"{step_name}.start", **context)
    extra: dict = {}
    start = time.perf_counter()
    try:
        yield extra
    except Exception as exc:
        dur = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            f"{step_name}.error",
            duration_ms=dur,
            error=str(exc),
            exc_info=True,
            **{**context, **extra},
        )
        raise
    else:
        dur = round((time.perf_counter() - start) * 1000, 2)
        logger.info(f"{step_name}.end", duration_ms=dur, **{**context, **extra})


def traced(logger: Any, name: str | None = None) -> Callable:
    """Decorator wrapping a function in :func:`log_step`.

    Works for BOTH sync and async functions::

        @traced(log)                       # step name = function __name__
        async def fetch_emails(...): ...

        @traced(log, name="agent.intake.run")
        def run(...): ...
    """

    def decorator(func: Callable) -> Callable:
        step = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                with log_step(logger, step):
                    return await func(*args, **kwargs)

            return awrapper

        @functools.wraps(func)
        def swrapper(*args: Any, **kwargs: Any) -> Any:
            with log_step(logger, step):
                return func(*args, **kwargs)

        return swrapper

    return decorator
