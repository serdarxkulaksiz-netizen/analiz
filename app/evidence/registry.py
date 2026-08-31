"""Evidence registry (plan.md A5 / real-spec Bölüm 3).

Maps attachments to Evidence classes by `(mime_type, device_id)` — no file-name
`if`s. The active Profile decides which evidence goes to the LLM / to the store
and which content rules shape each one; both are injected per call.

Attachments with no matching class are skipped for the LLM mapping, but note
that downloading/storing raw files happens in the Source layer regardless —
nothing is silently dropped from disk.
"""

from app.evidence.base import Evidence
from app.evidence.profiles import Profile
from app.evidence.rules import RuleContext
from app.evidence.types import (
    BrowserLogEvidence,
    HtmlEvidence,
    JenkinsLogEvidence,
    MobileScreenshotEvidence,
    TestLogEvidence,
    WebScreenshotEvidence,
)
from app.source.models import Attachment, RawScenario

_EVIDENCE_CLASSES: tuple[type[Evidence], ...] = (
    TestLogEvidence,
    BrowserLogEvidence,
    JenkinsLogEvidence,
    HtmlEvidence,
    WebScreenshotEvidence,
    MobileScreenshotEvidence,
)


class EvidenceRegistry:
    """Builds Evidence instances for a scenario, flagged and ruled by profile."""

    def _class_for(self, attachment: Attachment) -> type[Evidence] | None:
        for cls in _EVIDENCE_CLASSES:
            if cls.matches(attachment):
                return cls
        return None

    def build_for(
        self,
        scenario: RawScenario,
        profile: Profile,
        ctx: RuleContext | None = None,
    ) -> list[Evidence]:
        """One Evidence per mapped attachment; flags and rules come from profile."""
        context = ctx or RuleContext(
            scenario_name=scenario.scenario_name, error_text=scenario.error_text
        )
        evidences: list[Evidence] = []
        for attachment in scenario.attachments:
            cls = self._class_for(attachment)
            if cls is None:
                continue
            evidences.append(
                cls.from_attachment(
                    attachment,
                    goes_to_llm=cls.evidence_name in profile.evidence_to_llm,
                    goes_to_store=cls.evidence_name in profile.evidence_to_store,
                    rules=profile.rules_for(cls.evidence_name),
                    ctx=context,
                )
            )
        return evidences
