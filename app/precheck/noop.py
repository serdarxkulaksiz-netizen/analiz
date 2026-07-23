"""NoOpPreCheck — the only implementation today (plan.md A7).

Always returns None: every scenario goes to the LLM. NO rules, no match lists,
no known-issues table, no pattern database — this emptiness is a deliberate
decision (rule accumulation broke maintainability in the old project). Future
needs get a NEW PreCheck implementation added to the registry; upper code stays
unchanged.
"""

from app.domain.findings import Findings
from app.domain.result import LLMAnalysis
from app.precheck.base import PreCheck


class NoOpPreCheck(PreCheck):
    """Never short-circuits; always defers to the LLM."""

    def check(self, findings: Findings) -> LLMAnalysis | None:
        return None
