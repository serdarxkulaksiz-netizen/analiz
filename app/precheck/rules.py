"""PreCheck rules — config-defined shortcuts that skip the LLM."""

import json
import re
from pathlib import Path

from pydantic import BaseModel, field_validator


class PreCheckRule(BaseModel):
    """One shortcut: if `match` is found, answer with these fields."""

    name: str
    match: str

    verdict: str
    confidence: float
    root_cause: str = ""
    error_type: str = ""
    explanation: str = ""
    suggestion: str = ""
    confidence_reason: str = ""
    summary: str = ""
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

    @field_validator("verdict")
    @classmethod
    def _known_verdict(cls, value: str) -> str:
        from app.domain.enums import Verdict

        try:
            Verdict(value)
        except ValueError:
            known = ", ".join(v.value for v in Verdict)
            raise ValueError(f"unknown verdict {value!r}. Known: {known}") from None
        return value

    def matches(self, evidence_text: str) -> bool:
        """True if this rule's pattern is found in the evidence sent to the LLM."""
        return re.search(self.match, evidence_text) is not None


def load_rules(config_path: Path, confidence_buckets: list[float]) -> list[PreCheckRule]:
    """Load and validate the rule list; raises on bad config (fail fast).

    `confidence` is checked against the CONFIGURED buckets, not a copy of them:
    the prompt tells the model one set of values, and a precheck answer that
    used a different set would be the same field with two meanings.
    """
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{config_path} must contain a JSON list of rules.")
    allowed = set(confidence_buckets)
    rules: list[PreCheckRule] = []
    for index, row in enumerate(data):
        try:
            rule = PreCheckRule.model_validate(row)
        except ValueError as exc:
            raise ValueError(f"{config_path} rule #{index}: {exc}") from exc
        if rule.confidence not in allowed:
            raise ValueError(
                f"{config_path} rule #{index}: confidence {rule.confidence} "
                f"CONFIDENCE_BUCKETS içinde yok (geçerli: {sorted(allowed)})"
            )
        rules.append(rule)
    return rules
