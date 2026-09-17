"""OpenAI-compatible LLM provider — real service, single-shot."""

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
            raise ValueError("LLM_BASE_URL is empty — set it in .env.")
        self._url = base_url.rstrip("/") + endpoint_path
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._verify_ssl = verify_ssl
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def complete(self, prompt: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        request = {
            "url": self._url,
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        client_kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        else:
            client_kwargs["verify"] = self._verify_ssl

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(self._url, json=payload, headers=self._headers())
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        raw_response = response.text
        duration_ms = int((time.perf_counter() - started) * 1000)

        content, model, input_tokens, output_tokens = self._extract(response, raw_response)
        return LLMResponse(
            content=content,
            raw_response=raw_response,
            request=request,
            http_status=response.status_code,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

    def _extract(
        self, response: httpx.Response, raw_response: str
    ) -> tuple[str, str, int | None, int | None]:
        """Best-effort extraction; on failure return empty content (raw is kept)."""
        if not response.is_success:
            return "", "", None, None
        try:
            data: Any = response.json()
            if isinstance(data, str):
                data = json.loads(data)
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return (
                content or "",
                str(data.get("model") or ""),
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
        except Exception:
            return "", "", None, None
