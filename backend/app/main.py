"""FastAPI application entry point.

Wires the API routers, the standard response/error envelopes (§4.2), CORS for
the Next.js frontend, and starts the Flow scheduler (5-min Gmail poll) on
startup.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.api.routes import (
    analytics,
    auth,
    candidates,
    files,
    integrations_gmail,
    interviews,
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
    # Open the ngrok tunnel first so backend_base_url points at the public URL
    # before any Twilio webhook callback is built (no-op unless NGROK_ENABLED).
    from app.services.tunnel import start_tunnel, stop_tunnel

    start_tunnel()
    try:
        from app.services.scheduler import start_scheduler, shutdown_scheduler

        start_scheduler()
        log.info("startup_complete", env=settings.app_env, llm_provider=settings.llm_provider,
                 backend_base_url=settings.backend_base_url)
        yield
        shutdown_scheduler()
    except Exception as exc:  # scheduler is best-effort; API must still serve
        log.warning("scheduler_unavailable", error=str(exc))
        yield
    finally:
        stop_tunnel()


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
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Exception handlers → standard error envelope (§4.2) ----------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed",
                           "detail": str(exc.errors())}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred",
                           "detail": str(exc) if settings.app_env == "development" else None}},
    )


# ---------------- Routers ----------------
for r in (auth.router, candidates.router, requisitions.router, skills.router, meta.router,
          users.router, screening.router, interviews.router, analytics.router,
          webhooks.router, files.router, integrations_gmail.router):
    app.include_router(r)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider}


@app.get("/", tags=["health"])
def root():
    return {"name": "Recruitment Platform (ATS) API", "docs": "/docs", "health": "/health"}
