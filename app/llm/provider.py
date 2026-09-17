"""LLMProvider interface — agentless, single-shot."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Raised when the LLM call fails (timeout, transport, malformed reply)."""


class LLMResponse(BaseModel):
    """Raw completion plus call metadata for the `meta` block."""

    content: str
    raw_response: str = ""
    request: dict = {}
    http_status: int = 0
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int = 0


class LLMProvider(ABC):
    """Pluggable LLM boundary: one prompt in, one completion out."""

    @abstractmethod
    async def complete(self, prompt: str) -> LLMResponse:
        """Send a single prompt, return the single raw completion."""
