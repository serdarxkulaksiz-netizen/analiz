"""NoOpPreCheck — the only implementation today."""

from app.domain.findings import Findings
from app.domain.result import LLMAnalysis
from app.precheck.base import PreCheck


class NoOpPreCheck(PreCheck):
    """Never short-circuits; always defers to the LLM."""

    def check(self, findings: Findings) -> LLMAnalysis | None:
        return None
