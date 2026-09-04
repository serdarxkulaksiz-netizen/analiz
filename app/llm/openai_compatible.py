"""OpenAI-compatible LLM provider (plan.md A9) — real service, single-shot.

Sends the prompt as one `user` message to `base_url + endpoint_path` and reads
`choices[0].message.content` from the OpenAI-style `chat.completion` response.

Verified against the real service (test-automation-ai-api …/api/v1/extension/send):
  - NO auth: the service takes no token; an `Authorization` header is sent only
    if an api_key is explicitly configured (empty by default).
  - The request body carries `messages` + `temperature` + `max_tokens`. The
    `model` field is NOT sent in the body (it is meta only).

All call parameters (base URL, path, temperature, timeout, max_tokens) come
from config — nothing hardcoded. A custom transport can be injected for tests.
"""

import json
import time
from typing import Any

import httpx

from app.llm.provider import LLMError, LLMProvider, LLMResponse


class OpenAICompatibleLLMProvider(LLMProvider):
    """Single-shot call against an OpenAI-compatible chat endpoint (on-prem)."""

    def __init__(
        self,
        base_url: str,
        endpoint_path: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout_seconds: float,
        max_tokens: int,
        verify_ssl: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("LLM_BASE_URL is empty — set it in .env (or use LLM_PROVIDER=mock).")
        self._url = base_url.rstrip("/") + endpoint_path
        self._api_key = api_key
        self._model = model  # kept for meta only; not sent in the body
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._verify_ssl = verify_ssl
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self._api_key:  # this service needs none; generic support only
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def complete(self, prompt: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        # Full request for the trace (model is logged here but NOT sent in body).
        request = {"url": self._url, "model": self._model, **payload}

        client_kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
        # A custom transport (tests) handles its own connection; `verify` only
        # applies to the real default transport.
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        else:
            client_kwargs["verify"] = self._verify_ssl

        started = time.perf_counter()
        # A transport-level failure (timeout / no connection) yields no envelope
        # to keep — only that raises LLMError.
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(self._url, json=payload, headers=self._headers())
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        # We HAVE a response: capture the full raw envelope BEFORE any parsing,
        # so it is never lost even if the body is malformed (plan.md A9/A10).
        raw_response = response.text
        duration_ms = int((time.perf_counter() - started) * 1000)

        content, model, input_tokens, output_tokens = self._extract(response, raw_response)
        return LLMResponse(
            content=content,
            raw_response=raw_response,
            request=request,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

    def _extract(
        self, response: httpx.Response, raw_response: str
    ) -> tuple[str, str, int | None, int | None]:
        """Best-effort extraction; on failure return empty content (raw is kept)."""
        try:
            data: Any = response.json()
            # The intermediary may double-encode (a JSON string of JSON).
            if isinstance(data, str):
                data = json.loads(data)
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return (
                content or "",
                data.get("model", self._model),
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
        except Exception:
            # Malformed / unexpected envelope: leave content empty; the caller
            # marks the scenario analysis_failed but the raw envelope is saved.
            return "", self._model, None, None
