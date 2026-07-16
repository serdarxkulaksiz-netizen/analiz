"""OpenAI-compatible LLM provider (plan.md A9) — endpoint passthrough.

Sends `messages` to a full chat-completions URL taken from config, reads
`choices[0].message.content`. All call parameters (URL, key, model,
temperature, timeout, max_tokens) come from config — nothing hardcoded.
"""

import time
from typing import Any

import httpx

from app.llm.provider import LLMError, LLMProvider, LLMResponse


class OpenAICompatibleLLMProvider(LLMProvider):
    """Single-shot call against any OpenAI-compatible endpoint (on-prem local LLM)."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout_seconds: float,
        max_tokens: int | None = None,
    ) -> None:
        if not api_url:
            raise ValueError(
                "LLM_API_URL is empty — set the full OpenAI-compatible "
                "chat-completions URL in .env (or use LLM_PROVIDER=mock)."
            )
        self._api_url = api_url
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens

    async def complete(self, prompt: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        duration_ms = int((time.perf_counter() - started) * 1000)

        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            duration_ms=duration_ms,
        )
