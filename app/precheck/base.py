"""PreCheck interface."""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.domain.result import LLMAnalysis


class PreCheck(ABC):
    """Optional short-circuit evaluated before the LLM call."""

    @abstractmethod
    def check(self, findings: Findings) -> LLMAnalysis | None:
        """Return a ready analysis to skip the LLM, or None to proceed."""
