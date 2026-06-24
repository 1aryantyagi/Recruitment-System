"""Application configuration.

Reads every value from environment variables (loaded from the repo-root `.env`
during local development). All external-integration keys are optional — when a
key is absent the corresponding integration degrades gracefully (mock / skip),
so the system always boots and the pipeline always completes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SECRET_KEY values that must never sign tokens in a real deployment.
_WEAK_SECRETS = {"", "dev-secret-change-me", "dev-secret-change-me-in-production"}

# Repo-root .env (…/Recruitment-System/.env), resolved from this file's location
# so config loads correctly no matter the current working directory. A
# backend-local ".env" (if present) overrides it.
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_env: Literal["development", "staging", "production"] = "development"
    secret_key: str = "dev-secret-change-me"
    # Short-lived access JWT; the refresh token below keeps sessions alive.
    access_token_expire_minutes: int = 30
    # Long-lived, rotated, revocable refresh token (stored hashed in the DB).
    refresh_token_expire_days: int = 14
    backend_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    # Browser-facing OAuth redirect base (Gmail "Connect" callback). That callback
    # is hit by the admin's own browser on this host — it does NOT need the public
    # internet — so it must stay on the stable local URL even when ngrok rewrites
    # backend_base_url to a public tunnel (which only Twilio's server-to-server
    # webhooks need, and which changes every restart on the free ngrok plan). Set
    # by the tunnel at startup; empty falls back to backend_base_url.
    oauth_redirect_base_url: str = ""

    # ---- Logging ----
    # Verbosity for BOTH stdout and app.log. DEBUG captures the technical traces
    # (step start/end, durations, external-call summaries); drop to INFO if noisy.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    # Directory for log files. Resolves to <backend>/logs locally and /app/logs in
    # the Docker image (WORKDIR=/app). Override with LOG_DIR. Created on startup.
    log_dir: str = str(Path(__file__).resolve().parents[1] / "logs")
    # Log filename (joined to log_dir unless an absolute path is given).
    log_file: str = "app.log"
    # Rotate at ~10 MB, keep 5 backups (app.log + app.log.1 .. app.log.5).
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    ngrok_enabled: bool = False
    ngrok_authtoken: str = ""

    # ---- Pipeline thresholds (0-100 in env; normalized to 0-1 where needed) ----
    resume_score_threshold: int = 70
    call_score_threshold: int = 70
    gmail_poll_interval_minutes: int = 5
    # Auto-email new email applicants for the logistics fields missing from their
    # resume (CTC, notice, availability, shift/work-mode), and parse their replies.
    detail_collection_enabled: bool = True

    # ---- Interview feedback collection (Teams + email) ----
    # Master switch for the post-interview feedback workflow (detection, request
    # emails, Teams/email monitoring, reminders, escalation).
    feedback_collection_enabled: bool = True
    # How often the feedback poll cycle runs (separate APScheduler job).
    feedback_poll_interval_minutes: int = 5
    # Grace period after scheduled_at before an interview is assumed concluded and
    # feedback collection starts (the spec's "2:00 PM scheduled, 2:30 PM -> done").
    interview_completion_buffer_minutes: int = 30
    # Auto-advance the JobApplication from the extracted recommendation (NO ->
    # REJECTED; STRONG_YES/YES on a final round -> OFFERED). Off keeps it record-only.
    feedback_auto_advance_enabled: bool = True
    # Minimum LLM confidence to accept a Teams message as feedback for a candidate.
    feedback_match_min_confidence: float = 0.6
    # Optional override recipient for 72h escalation; blank -> requisition hiring
    # manager (falling back to the interview creator).
    feedback_escalation_email: str = ""

    # ---- Database ----
    postgres_host: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "recruitment"
    postgres_user: str = "recruitment"
    postgres_password: str = "recruitment"

    # ---- Encryption (AES-256-GCM for sensitive fields at rest) ----
    encryption_key: str = ""

    # ---- LLM (provider-agnostic via LangChain) ----
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # ---- Gmail ----
    # Path A — Google Workspace service account (zero refresh token). When both
    # are set, this takes precedence over the OAuth paths below.
    google_service_account_json: str = ""  # path to JSON key file OR inline JSON
    gmail_impersonate_email: str = ""       # Workspace mailbox to read, e.g. resumes@company.com
    # Path B — OAuth web client. client_id/secret drive the admin "Connect Gmail"
    # flow (refresh token stored encrypted in the DB). google_refresh_token is a
    # legacy .env fallback for the same client.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # ---- Microsoft Graph ----
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""

    # ---- Twilio ----
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # ---- Screening voice agent ----
    company_name: str = "Intelera"
    # IANA timezone the company books interviews in. Interviewer slot times
    # (e.g. 16:30) are interpreted as local to this zone; `interviews.scheduled_at`
    # is always stored in UTC. Used by the interviewer-slot engine.
    company_timezone: str = "Asia/Kolkata"
    # Caller persona name spoken in the intro; blank → "the talent team".
    screening_agent_name: str = ""
    # Amazon Polly Indian-English neural voice for a natural-sounding call.
    tts_voice: str = "Polly.Kajal-Neural"
    # Speech-recognition language hint for Twilio <Gather input="speech">.
    stt_language: str = "en-IN"

    # ---- Realtime voice streaming (low-latency speech-to-speech) ----
    # When true, the screening call streams audio over Twilio Media Streams to
    # OpenAI Realtime (speech-to-speech), with a parallel Deepgram tap for the
    # transcript. Off → the legacy turn-based <Gather>/<Say> IVR runs unchanged.
    voice_streaming_enabled: bool = False
    # OpenAI Realtime model (GA). Use "gpt-realtime" (most capable) or
    # "gpt-realtime-mini" (cheaper/faster). The legacy "*-realtime-preview" models
    # select the now-disabled beta API shape and fail with beta_api_shape_disabled.
    openai_realtime_model: str = "gpt-realtime"
    # Realtime voice (distinct from the Polly <Say> voice): alloy, echo, shimmer,
    # marin, cedar, … (whatever the chosen realtime model supports).
    realtime_voice: str = "alloy"
    # server_vad end-of-speech window (ms). Lower = snappier replies but more false
    # barge-ins; this is the main knob for tuning perceived voice-to-voice latency.
    realtime_silence_ms: int = 320

    # ---- Deepgram ----
    deepgram_api_key: str = ""
    # Streaming model for the live transcript tap on the candidate's audio. nova-2
    # is the proven en-IN streaming combo; nova-3 is more accurate where supported.
    deepgram_live_model: str = "nova-2"

    # ---------- Validation ----------
    @model_validator(mode="after")
    def _enforce_prod_secrets(self) -> "Settings":
        """Fail fast in staging/production if the JWT secret is weak/default.

        A default SECRET_KEY in a real deployment lets anyone forge tokens, so we
        refuse to boot rather than run insecurely. Dev stays permissive."""
        if self.app_env in {"staging", "production"}:
            if self.secret_key.strip() in _WEAK_SECRETS:
                raise ValueError(
                    "SECRET_KEY must be set to a strong, unique value in "
                    f"{self.app_env} (the dev default is not allowed)."
                )
            if not self.encryption_key.strip():
                raise ValueError(
                    f"ENCRYPTION_KEY must be set in {self.app_env} so encrypted "
                    "fields don't fall back to a key derived from SECRET_KEY."
                )
        return self

    # ---------- Derived helpers ----------
    @property
    def public_ws_base_url(self) -> str:
        """``backend_base_url`` as a WebSocket origin (wss for https), for the
        Twilio ``<Stream url=…>`` callback. Under ngrok, ``backend_base_url`` is
        already rewritten to the public https tunnel at startup (tunnel.py)."""
        base = self.backend_base_url.rstrip("/")
        if base.startswith("https://"):
            return "wss://" + base[len("https://"):]
        if base.startswith("http://"):
            return "ws://" + base[len("http://"):]
        return base

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def llm_provider(self) -> Literal["anthropic", "openai", "none"]:
        """Anthropic takes precedence when its key is present; else OpenAI; else stub."""
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "none"

    @property
    def resume_threshold_ratio(self) -> float:
        return self.resume_score_threshold / 100.0

    @property
    def call_threshold_ratio(self) -> float:
        return self.call_score_threshold / 100.0

    # Capability flags used to decide mock vs live integration paths.
    @property
    def twilio_enabled(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_phone_number)

    @property
    def gmail_enabled(self) -> bool:
        """Legacy .env OAuth path: a static refresh token plus its client creds.

        This is only one input to whether Gmail is usable — the broader,
        DB- and service-account-aware check lives in the Gmail client
        (`gmail.gmail_configured()`)."""
        return bool(self.google_client_id and self.google_client_secret and self.google_refresh_token)

    @property
    def gmail_service_account_enabled(self) -> bool:
        """Path A: a Workspace service account configured to impersonate a mailbox."""
        return bool(self.google_service_account_json and self.gmail_impersonate_email)

    @property
    def ms_graph_enabled(self) -> bool:
        return bool(self.ms_tenant_id and self.ms_client_id and self.ms_client_secret)

    @property
    def deepgram_enabled(self) -> bool:
        return bool(self.deepgram_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
