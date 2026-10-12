"""Known errors — answers kept in a file, matched on step + error message."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.enums import Verdict
from app.domain.findings import Findings
from app.domain.result import LLMAnalysis
from app.precheck.base import PreCheck

ANSWERED_BY = "known_errors"


class KnownError(BaseModel):
    """One catalogued failure: this step with this message means this."""

    model_config = ConfigDict(extra="forbid")

    step: str
    error: str
    answer: str
    verdict: str
    confidence: float

    @field_validator("step", "error", "answer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("verdict")
    @classmethod
    def _known_verdict(cls, value: str) -> str:
        try:
            Verdict(value)
        except ValueError:
            known = ", ".join(v.value for v in Verdict)
            raise ValueError(f"unknown verdict {value!r}. Known: {known}") from None
        return value

    @property
    def key(self) -> tuple[str, str]:
        return self.step.strip(), self.error.strip()


class KnownErrorsPreCheck(PreCheck):
    """Answers a scenario from the catalogue instead of calling the model."""

    answered_by = ANSWERED_BY

    def __init__(self, known: list[KnownError]) -> None:
        self._by_key = {row.key: row for row in known}

    def check(self, findings: Findings) -> LLMAnalysis | None:
        """Exact match on both halves of the key, or no answer at all.

        An empty step or an empty error message never matches: a scenario the
        source said nothing about would otherwise collect the catalogue's first
        answer with an empty key, and hundreds of scenarios would share one
        diagnosis nobody wrote for them.
        """
        report = findings.evidence_report
        key = (report.failed_step.strip(), report.error_text.strip())
        if not all(key):
            return None
        row = self._by_key.get(key)
        if row is None:
            return None
        return LLMAnalysis(
            explanation=row.answer,
            verdict=Verdict(row.verdict),
            confidence=row.confidence,
            confidence_reason="bilinen hatalar listesinden birebir eşleşti",
        )


def load_known_errors(config_path: Path, confidence_buckets: list[float]) -> list[KnownError]:
    """Load and validate the catalogue; raises on bad config (fail fast)."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{config_path} must contain a JSON list of known errors.")
    allowed = set(confidence_buckets)
    rows: list[KnownError] = []
    seen: dict[tuple[str, str], int] = {}
    for index, raw in enumerate(data):
        try:
            row = KnownError.model_validate(raw)
        except ValueError as exc:
            raise ValueError(f"{config_path} #{index}: {exc}") from exc
        if row.confidence not in allowed:
            raise ValueError(
                f"{config_path} #{index}: confidence {row.confidence} CONFIDENCE_BUCKETS "
                f"içinde yok (geçerli: {sorted(allowed)})"
            )
        first = seen.get(row.key)
        if first is not None:
            raise ValueError(
                f"{config_path} #{index}: aynı adım + hata çifti #{first} satırında da var — "
                "hangi cevabın geçerli olduğu belirsiz kalırdı."
            )
        seen[row.key] = index
        rows.append(row)
    return rows


__all__ = ["ANSWERED_BY", "KnownError", "KnownErrorsPreCheck", "load_known_errors"]
