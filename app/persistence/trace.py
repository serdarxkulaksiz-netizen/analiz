"""The one thing that may reach the disk: what we sent and what came back."""

import json
from pathlib import Path
from typing import Any


def safe_path_part(value: str) -> str:
    """Make an id/name safe to use as a single filesystem path segment."""
    return value.replace("/", "_").replace(":", "_").replace("\\", "_")


class TraceWriter:
    """Writes one prompt and one response per analyzed scenario, or nothing.

    Off by default: with no directory configured nothing is written and no
    folder is created. It exists for one question — "what exactly did the model
    see, and what exactly did it answer" — and holds nothing else.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def enabled(self) -> bool:
        return self._root is not None

    def write(
        self,
        analyzer_run_id: str,
        scenario_name: str,
        *,
        prompt: str,
        response: dict[str, Any],
    ) -> None:
        """Write this scenario's prompt and response; no prompt, no files."""
        if self._root is None or not prompt:
            return
        folder = self._root / safe_path_part(analyzer_run_id)
        folder.mkdir(parents=True, exist_ok=True)
        name = safe_path_part(scenario_name) or "scenario"
        (folder / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
        (folder / f"{name}.response.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
        )


__all__ = ["TraceWriter", "safe_path_part"]
