"""RuleBasedPreCheck — answers known failures without calling the LLM (plan.md A7).

Rules come from config (see `rules.py`). The FIRST matching rule wins, in file
order, so precedence is explicit and predictable. No match -> `None` -> the
scenario takes the normal LLM path.

The answer is a normal `LLMAnalysis`, so everything downstream (parsing,
persistence, the API response) is unchanged. Two things make the shortcut
visible in the stored result: `meta.llm_model` is set to `precheck` by the
service, and the rule's `error_signature` says which rule answered.
"""

from app.domain.enums import Verdict
from app.domain.findings import Findings
from app.domain.result import LLMAnalysis
from app.precheck.base import PreCheck
from app.precheck.rules import PreCheckRule


class RuleBasedPreCheck(PreCheck):
    """Short-circuits scenarios whose failure matches a configured rule."""

    def __init__(self, rules: list[PreCheckRule]) -> None:
        self._rules = rules

    def check(self, findings: Findings) -> LLMAnalysis | None:
        if not self._rules:
            return None
        evidence_text = "\n".join(
            block.content for block in findings.evidence_blocks if block.content
        )
        for rule in self._rules:
            if rule.matches(findings.error_message, evidence_text):
                return LLMAnalysis(
                    scenario_name=findings.scenario_name,
                    root_cause=rule.root_cause,
                    error_type=rule.error_type,
                    verdict=Verdict(rule.verdict),
                    explanation=rule.explanation,
                    suggestion=rule.suggestion,
                    confidence=rule.confidence,
                    confidence_reason=rule.confidence_reason,
                    summary=rule.summary,
                    error_signature=rule.error_signature or rule.name,
                )
        return None
