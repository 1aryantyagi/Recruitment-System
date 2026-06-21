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

from pydantic_settings import BaseSettings, SettingsConfigDict

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
    access_token_expire_minutes: int = 480
    backend_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    # Browser-facing OAuth redirect base (Gmail "Connect" callback). That callback
    # is hit by the admin's own browser on this host — it does NOT need the public
    # internet — so it must stay on the stable local URL even when ngrok rewrites
    # backend_base_url to a public tunnel (which only Twilio's server-to-server
    # webhooks need, and which changes every restart on the free ngrok plan). Set
    # by the tunnel at startup; empty falls back to backend_base_url.
    oauth_redirect_base_url: str = ""

    ngrok_enabled: bool = False
    ngrok_authtoken: str = ""

    # ---- Pipeline thresholds (0-100 in env; normalized to 0-1 where needed) ----
    resume_score_threshold: int = 70
    call_score_threshold: int = 70
    gmail_poll_interval_minutes: int = 5
    # Auto-email new email applicants for the logistics fields missing from their
    # resume (CTC, notice, availability, shift/work-mode), and parse their replies.
    detail_collection_enabled: bool = True

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
