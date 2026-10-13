"""PreCheck interface."""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.domain.findings import Findings
from app.domain.result import LLMAnalysis


class PreCheck(ABC):
    """Optional short-circuit evaluated before the LLM call."""

    #: What goes into `meta.answered_by` when this implementation answers, so a
    #: stored row names the thing that actually produced the diagnosis.
    answered_by: ClassVar[str] = "precheck"

    #: True when the check reads the evidence TEXT, so it can only run after the
    #: files have been read. False when the scenario's own facts are enough —
    #: then it runs BEFORE anything is fetched, and a match costs no traffic at
    #: all. Default True: a new implementation has to say it is cheap.
    needs_evidence: ClassVar[bool] = True

    @abstractmethod
    def check(self, findings: Findings) -> LLMAnalysis | None:
        """Return a ready analysis to skip the LLM, or None to proceed."""
