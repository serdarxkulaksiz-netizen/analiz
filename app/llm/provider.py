"""LLMProvider interface (plan.md A9) — agentless, single-shot.

One prompt in, one completion out. No tool-calling, no iterative loops
(plan.md B3.7). Providers are swapped via config, upper code never changes.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Raised when the LLM call fails (timeout, transport, malformed reply).

    The caller marks the scenario `analysis_failed` and the job continues
    (plan.md A9 — one scenario never brings down the whole run).
    """


class LLMResponse(BaseModel):
    """Raw completion plus call metadata for the `meta` block (plan.md A8/A10).

    `content` is the message content (the diagnosis JSON, fed to `_try_json`).
    `raw_response` is the FULL response envelope as text (id/choices/usage/model
    — everything), kept for the trace even when parsing fails. `request` is the
    full request that was sent (url + body + model), for the `prompts` trace.
    """

    content: str
    raw_response: str = ""
    request: dict = {}
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int = 0


class LLMProvider(ABC):
    """Pluggable LLM boundary (Halka 4)."""

    @abstractmethod
    async def complete(self, prompt: str) -> LLMResponse:
        """Send a single prompt, return the single raw completion."""
