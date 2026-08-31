"""PreCheck rules — config-defined shortcuts that skip the LLM (plan.md A7).

Some failures need no analysis: "the DB credentials changed" looks the same in
many projects and runs. A rule matches such a failure and returns a ready-made
answer, so the LLM is never called.

Rules live in config (`config/precheck_rules.json`), never in code: a new case
is a new row. Everything is validated when the file is loaded — a bad regex,
an unknown verdict or an off-bucket confidence fails at startup, not mid-run.

CAUTION (plan.md A7): a rule bypasses the LLM entirely, so a pattern that is
too broad will mislabel everything and nobody will notice. Keep the list short
and the patterns narrow (exact signatures like `ORA-01017`; never bare words
like `error`/`failed`).
"""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator

#: Where a rule looks for its pattern.
SearchIn = Literal["error_message", "evidence"]

#: Allowed confidence values (plan.md A10) — same buckets as the LLM's.
_CONFIDENCE_BUCKETS = {0.1, 0.25, 0.5, 0.75, 0.99}


class PreCheckRule(BaseModel):
    """One shortcut: if `match` is found, answer with these fields."""

    name: str
    match: str  # regex
    search_in: SearchIn = "error_message"

    # --- the canned diagnosis (text written by a human, not fabricated) ---
    verdict: str
    confidence: float
    root_cause: str = ""
    error_type: str = ""
    explanation: str = ""
    suggestion: str = ""
    confidence_reason: str = ""
    summary: str = ""
    #: Which rule answered — surfaces in the stored result (plan.md A10).
    error_signature: str = ""

    @field_validator("name", "match")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("match")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return value

    @field_validator("confidence")
    @classmethod
    def _known_bucket(cls, value: float) -> float:
        if value not in _CONFIDENCE_BUCKETS:
            raise ValueError(
                f"confidence must be one of {sorted(_CONFIDENCE_BUCKETS)}, got {value}"
            )
        return value

    @field_validator("verdict")
    @classmethod
    def _known_verdict(cls, value: str) -> str:
        from app.domain.enums import Verdict  # local: avoid import cycle at module load

        try:
            Verdict(value)
        except ValueError:
            known = ", ".join(v.value for v in Verdict)
            raise ValueError(f"unknown verdict {value!r}. Known: {known}") from None
        return value

    def matches(self, error_message: str, evidence_text: str) -> bool:
        """True if this rule's pattern is found in the configured field."""
        haystack = evidence_text if self.search_in == "evidence" else error_message
        return re.search(self.match, haystack) is not None


def load_rules(config_path: Path) -> list[PreCheckRule]:
    """Load and validate the rule list; raises on bad config (fail fast)."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{config_path} must contain a JSON list of rules.")
    rules: list[PreCheckRule] = []
    for index, row in enumerate(data):
        try:
            rules.append(PreCheckRule.model_validate(row))
        except ValueError as exc:
            raise ValueError(f"{config_path} rule #{index}: {exc}") from exc
    return rules
