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

    ngrok_enabled: bool = False
    ngrok_authtoken: str = ""

    # ---- Pipeline thresholds (0-100 in env; normalized to 0-1 where needed) ----
    resume_score_threshold: int = 70
    call_score_threshold: int = 70
    gmail_poll_interval_minutes: int = 5

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

    # ---- Deepgram ----
    deepgram_api_key: str = ""

    # ---------- Derived helpers ----------
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
        return bool(self.google_client_id and self.google_client_secret and self.google_refresh_token)

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
