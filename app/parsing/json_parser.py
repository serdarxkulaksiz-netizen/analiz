"""`try_json` — the only parsing the system does on LLM output."""

import json
from typing import Any


def try_json(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from LLM output."""
    candidates: list[str] = []

    stripped = text.strip()
    candidates.append(stripped)

    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            inner = stripped[first_newline + 1 :]
            closing = inner.rfind("```")
            if closing != -1:
                inner = inner[:closing]
            candidates.append(inner.strip())

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
