"""PreCheck interface (plan.md A7).

Runs before the prompt is built. Input = the scenario's Findings; output =
`None` (continue to the normal LLM flow) OR a ready `LLMAnalysis` (skip the
LLM entirely). A new implementation is added via the registry; upper code does
not change.
"""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.domain.result import LLMAnalysis


class PreCheck(ABC):
    """Optional short-circuit evaluated before the LLM call."""

    @abstractmethod
    def check(self, findings: Findings) -> LLMAnalysis | None:
        """Return a ready analysis to skip the LLM, or None to proceed."""
