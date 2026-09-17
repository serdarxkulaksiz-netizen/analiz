"""Thin VisiumGo HTTP client."""

from typing import Any
from urllib.parse import quote

import httpx

_BODY_SAMPLE_CHARS = 200


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
            raise ValueError("VISIUMGO_BASE_URL is empty — set it in .env.")
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
        if self._transport is not None:
            kwargs["transport"] = self._transport
        else:
            kwargs["verify"] = self._verify_ssl
        return httpx.AsyncClient(**kwargs)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET and decode JSON — naming the body when it is not JSON."""
        async with self._client() as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                body = response.text[:_BODY_SAMPLE_CHARS]
                raise ValueError(
                    f"{path}: cevap JSON değil "
                    f"(content-type: {response.headers.get('content-type', '?')}) — "
                    f"gelen: {body!r}"
                ) from exc

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
