"""Thin VisiumGo HTTP client (plan.md Halka 1, real-spec Bölüm 1 & 6).

A small wrapper around httpx — NOT an orchestrator. All requests carry
`Authorization: Bearer <token>`; base URL, token and timeout come from config
(never hardcoded). Dynamic path segments (scenario id, file name) must be
URL-encoded by the caller with `encode_segment` before being placed in a path,
because they contain `/`, `:` and spaces.

A custom `httpx.AsyncBaseTransport` can be injected for tests (no real server).
"""

from typing import Any
from urllib.parse import quote

import httpx


def encode_segment(segment: str) -> str:
    """Percent-encode a value going into a single URL path segment."""
    return quote(segment, safe="")


class VisiumGoClient:
    """Issues authenticated GET requests against a VisiumGo instance."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float,
        verify_ssl: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError(
                "VISIUMGO_BASE_URL is empty — set it in .env (or use SOURCE_PROVIDER=mock)."
            )
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._verify_ssl = verify_ssl
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": self._base_url,
            "headers": self._headers(),
            "timeout": self._timeout,
        }
        # A custom transport (tests) handles its own connection; `verify` only
        # applies to the real default transport.
        if self._transport is not None:
            kwargs["transport"] = self._transport
        else:
            kwargs["verify"] = self._verify_ssl
        return httpx.AsyncClient(**kwargs)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with self._client() as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def get_text(self, path: str) -> str:
        async with self._client() as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.text

    async def get_bytes(self, path: str) -> bytes:
        async with self._client() as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.content
