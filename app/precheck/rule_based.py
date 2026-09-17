"""RuleBasedPreCheck — answers known failures without calling the LLM."""

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
            if rule.matches(evidence_text):
                return LLMAnalysis(
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
