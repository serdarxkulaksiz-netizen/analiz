"""OpenAICompatibleLLMProvider tests with an injected fake HTTP transport.

Verifies the real-service contract: correct URL, NO auth header, `model` NOT in
the body, temperature/max_tokens sent, and content/usage/model parsed. No real
server is contacted.
"""

import json

import httpx
import pytest

from app.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.llm.provider import LLMError

_CAPTURED: list[httpx.Request] = []

_OK_RESPONSE = {
    "id": "chatcmpl-a0358030",
    "choices": [
        {
            "finish_reason": "stop",
            "index": 0,
            "message": {"content": "{\"verdict\": \"unknown\"}", "role": "assistant"},
        }
    ],
    "created": 1785148332,
    "model": "qwen3-coder-next",
    "object": "chat.completion",
    "usage": {"completion_tokens": 3, "prompt_tokens": 15, "total_tokens": 18},
}


def _provider(handler, **overrides) -> OpenAICompatibleLLMProvider:
    _CAPTURED.clear()
    kwargs = dict(
        base_url="https://llm.test.local",
        endpoint_path="/api/v1/extension/send",
        api_key="",
        model="qwen3-coder-next",
        temperature=0.0,
        timeout_seconds=5.0,
        max_tokens=8000,
        transport=httpx.MockTransport(handler),
    )
    kwargs.update(overrides)
    return OpenAICompatibleLLMProvider(**kwargs)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    _CAPTURED.append(request)
    return httpx.Response(200, json=_OK_RESPONSE)


@pytest.mark.asyncio
async def test_request_shape_and_response_parsing() -> None:
    provider = _provider(_ok_handler)
    result = await provider.complete("kanıtlar burada")

    # Response parsing.
    assert result.content == '{"verdict": "unknown"}'
    assert result.model == "qwen3-coder-next"
    assert result.input_tokens == 15
    assert result.output_tokens == 3

    # Request shape.
    req = _CAPTURED[0]
    assert str(req.url) == "https://llm.test.local/api/v1/extension/send"
    assert "Authorization" not in req.headers  # this service has no auth
    body = json.loads(req.content)
    assert "model" not in body  # model is meta only, never in the body
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 8000
    assert body["messages"] == [{"role": "user", "content": "kanıtlar burada"}]


@pytest.mark.asyncio
async def test_api_key_adds_bearer_header_when_set() -> None:
    provider = _provider(_ok_handler, api_key="secret")
    await provider.complete("x")
    assert _CAPTURED[0].headers.get("Authorization") == "Bearer secret"


@pytest.mark.asyncio
async def test_empty_choices_raises_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [], "model": "m"})

    provider = _provider(handler)
    with pytest.raises(LLMError):
        await provider.complete("x")


@pytest.mark.asyncio
async def test_http_error_raises_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = _provider(handler)
    with pytest.raises(LLMError):
        await provider.complete("x")


def test_empty_base_url_fails_fast() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleLLMProvider(
            base_url="",
            endpoint_path="/x",
            api_key="",
            model="m",
            temperature=0.0,
            timeout_seconds=5.0,
            max_tokens=8000,
        )
