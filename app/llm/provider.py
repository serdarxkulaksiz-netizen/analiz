"""LLMProvider interface — agentless, single-shot.

One prompt in, one completion out. No tool-calling, no iterative loops
. Providers are swapped via config, upper code never changes.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Raised when the LLM call fails (timeout, transport, malformed reply).

    The caller marks the scenario `analysis_failed` and the job continues
     — one scenario never brings down the whole run).
    """


class LLMResponse(BaseModel):
    """Raw completion plus call metadata for the `meta` block.

    `content` is the message content (the diagnosis JSON, fed to `try_json`).
    `raw_response` is the FULL response envelope as text (id/choices/usage/model
    — everything), kept for the trace even when parsing fails.

    `request` is what the call was made WITH — url, model, temperature, token
    cap — and deliberately not the prompt itself. The prompt is the `prompts`
    row's own field; carrying it here too wrote the same 3.5 KB twice into one
    file and doubled that row for nothing.
    """

    content: str
    raw_response: str = ""
    request: dict = {}
    #: HTTP status of the answer (0 = the call never reached a response).
    #: Without it, "the model returned nonsense" and "the server returned 500"
    #: both look like an empty `content`.
    http_status: int = 0
    #: The model the SERVICE said answered. Empty when it did not say, or when
    #: nothing answered at all — the model we asked for is in `request`.
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int = 0


class LLMProvider(ABC):
    """Pluggable LLM boundary: one prompt in, one completion out."""

    @abstractmethod
    async def complete(self, prompt: str) -> LLMResponse:
        """Send a single prompt, return the single raw completion."""
