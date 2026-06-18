"""Provider-agnostic LLM layer (LangChain).

Resolves to Claude (`langchain-anthropic`) when ANTHROPIC_API_KEY is set,
otherwise OpenAI (`langchain-openai`) using OPENAI_MODEL. Swapping providers is
a one-line change here — no agent code changes.

Every structured call uses LangChain `with_structured_output(PydanticModel)`,
so agents receive validated objects instead of parsing model text. Untrusted
content (resume / transcript text) is always passed in the *human* message,
never concatenated into the system instructions (§12 prompt-injection rule).
"""
from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)

# Tier -> model name. For OpenAI we use the single configured model for all
# tiers; for Anthropic we map to the cost/quality-appropriate Claude model.
_ANTHROPIC_TIERS = {
    "analysis": "claude-opus-4-8",
    "extraction": settings.anthropic_model or "claude-sonnet-4-6",
    "short": "claude-haiku-4-5",
}


class LLMUnavailable(RuntimeError):
    """Raised when no LLM provider is configured."""


def llm_available() -> bool:
    return settings.llm_provider != "none"


def _build_model(tier: str, max_tokens: int):
    provider = settings.llm_provider
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=_ANTHROPIC_TIERS.get(tier, _ANTHROPIC_TIERS["extraction"]),
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=max_tokens,
            timeout=60,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        # temperature is intentionally left default — some newer OpenAI models
        # reject non-default temperatures.
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            timeout=60,
            max_retries=0,  # tenacity handles retries below
        )
    raise LLMUnavailable("No LLM provider configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def complete_structured(tier: str, system: str, human: str, schema: type[T], *, max_tokens: int = 2048) -> T:
    """Return a validated instance of `schema`. Raises LLMUnavailable if no provider."""
    model = _build_model(tier, max_tokens)
    structured = model.with_structured_output(schema)
    result = structured.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return result  # already a `schema` instance


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def complete_text(tier: str, system: str, human: str, *, max_tokens: int = 1024) -> str:
    """Return free-text completion (e.g. analytics digest)."""
    model = _build_model(tier, max_tokens)
    resp = model.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return resp.content if isinstance(resp.content, str) else str(resp.content)
