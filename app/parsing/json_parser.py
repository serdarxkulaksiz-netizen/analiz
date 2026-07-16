"""`_try_json` — the only parsing the system does on LLM output (plan.md B2.5).

No regex field extraction, no section parsing. We only try to locate a JSON
object in the completion (models sometimes wrap it in markdown fences or a
sentence). Anything that does not yield a JSON object returns None; the
caller then marks the scenario `analysis_failed` and keeps the raw response.
"""

import json
from typing import Any


def _try_json(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from LLM output."""
    candidates: list[str] = []

    stripped = text.strip()
    candidates.append(stripped)

    # Markdown code fence: keep only what is between the fences.
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            inner = stripped[first_newline + 1 :]
            closing = inner.rfind("```")
            if closing != -1:
                inner = inner[:closing]
            candidates.append(inner.strip())

    # Outermost braces: tolerate prose before/after the JSON object.
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
