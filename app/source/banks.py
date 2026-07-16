"""Bank registry — per-bank connection details from config (plan.md A0.1).

Bank info is never hardcoded: it lives in a JSON file whose path comes from
settings (`BANKS_CONFIG_PATH`). Structure of `BankConnection` stays loose on
purpose; exact fields firm up on the work PC when the real VisiumGo API is
seen (# TODO(work-pc)).
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class BankConnection(BaseModel):
    """Connection details for one bank's VisiumGo instance."""

    name: str
    visiumgo_base_url: str = ""
    jenkins_base_url: str = ""
    # Free-form slot for bank-specific settings not yet known
    # (# TODO(work-pc): firm up when real API access exists).
    extra: dict[str, Any] = {}


class BankRegistry:
    """Loads and serves BankConnection entries from the banks config file."""

    def __init__(self, config_path: Path) -> None:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        self._banks: dict[str, BankConnection] = {
            entry["name"]: BankConnection.model_validate(entry)
            for entry in data.get("banks", [])
        }

    def get(self, bank: str) -> BankConnection:
        """Return the bank's connection info; unknown bank is a config error."""
        if bank not in self._banks:
            known = ", ".join(sorted(self._banks)) or "<none>"
            raise ValueError(f"Unknown bank '{bank}'. Configured banks: {known}")
        return self._banks[bank]
