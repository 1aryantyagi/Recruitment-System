"""FastAPI application entry point.

Wires the API routers, the standard response/error envelopes (§4.2), CORS for
the Next.js frontend, and starts the Flow scheduler (5-min Gmail poll) on
startup.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger, log_step
from app.api.routes import (
    analytics,
    applications,
    auth,
    candidates,
    files,
    integrations_gmail,
    integrations_teams,
    interviews,
    media_stream,
    meta,
    requisitions,
    screening,
    skills,
    users,
    webhooks,
)

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("lifespan.startup.start", env=settings.app_env, llm_provider=settings.llm_provider)
    # Open the ngrok tunnel first so backend_base_url points at the public URL
    # before any Twilio webhook callback is built (no-op unless NGROK_ENABLED).
    from app.services.tunnel import start_tunnel, stop_tunnel

    with log_step(log, "lifespan.start_tunnel"):
        start_tunnel()
    try:
        from app.services.scheduler import start_scheduler, shutdown_scheduler

        with log_step(log, "lifespan.start_scheduler"):
            start_scheduler()
        log.info("startup_complete", env=settings.app_env, llm_provider=settings.llm_provider,
                 backend_base_url=settings.backend_base_url)
        yield
        log.info("lifespan.shutdown.start")
        with log_step(log, "lifespan.shutdown_scheduler"):
            shutdown_scheduler()
    except Exception as exc:  # scheduler is best-effort; API must still serve
        log.warning("scheduler_unavailable", error=str(exc), exc_info=True)
        yield
    finally:
        with log_step(log, "lifespan.stop_tunnel"):
            stop_tunnel()
        log.info("lifespan.shutdown.end")


app = FastAPI(
    title="Recruitment Platform (ATS) API",
    version="1.0.0",
    description="Internal ATS — 7 LangGraph agents over FastAPI. See product-req.md / technical-requirements.md.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    # Scoped to what the frontend actually uses rather than a blanket wildcard.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline security response headers. HSTS only in production (where
    TLS is terminated upstream); the others are safe everywhere."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if settings.app_env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Per-request start/end/error tracing for every HTTP endpoint.

    Binds a per-request ``request_id`` + method + path into structlog
    contextvars, so EVERY log line emitted while handling the request inherits
    them (correlation), then logs ``http.request.start`` / ``http.request.end``
    (status + duration) or ``http.request.error`` on an unhandled exception.

    NOTE: WebSocket routes (``media_stream`` under /webhooks) do NOT pass through
    BaseHTTPMiddleware, so they are traced inside their own handler.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        tokens = structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        log.info("http.request.start", query=str(request.url.query) or None,
                 client=request.client.host if request.client else None)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            dur = round((time.perf_counter() - start) * 1000, 2)
            log.error("http.request.error", duration_ms=dur, error=str(exc), exc_info=True)
            structlog.contextvars.reset_contextvars(**tokens)
            raise
        dur = round((time.perf_counter() - start) * 1000, 2)
        log.info("http.request.end", status_code=response.status_code, duration_ms=dur)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.reset_contextvars(**tokens)
        return response


# Added last → outermost layer, so its timing spans the full handler + the other
# middleware (Starlette middleware is LIFO: last-added runs first on the way in).
app.add_middleware(RequestLoggingMiddleware)


# ---------------- Exception handlers → standard error envelope (§4.2) ----------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    log.info("app_error", code=exc.code, status_code=exc.status_code, message=exc.message,
             path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    log.warning("validation_error", path=request.url.path, errors=str(exc.errors()))
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed",
                           "detail": str(exc.errors())}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred",
                           "detail": str(exc) if settings.app_env == "development" else None}},
    )


# ---------------- Routers ----------------
for r in (auth.router, candidates.router, requisitions.router, applications.router,
          skills.router, meta.router, users.router, screening.router, interviews.router,
          analytics.router, webhooks.router, media_stream.router, files.router,
          integrations_gmail.router, integrations_teams.router):
    app.include_router(r)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider}


@app.get("/", tags=["health"])
def root():
    return {"name": "Recruitment Platform (ATS) API", "docs": "/docs", "health": "/health"}
