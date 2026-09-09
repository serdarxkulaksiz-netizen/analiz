"""Evidence registry (plan.md A5 / real-spec Bölüm 3).

Maps attachments to Evidence classes by `(device_id, extension)` — no file-name
`if`s. The active Profile decides which evidence goes to the LLM / to the store
and which content rules shape each one; both are injected per call.

Attachments with no matching class are skipped for the LLM mapping, but they
are neither lost nor invisible: the Source downloads and stores every file
regardless, and extraction records the unmatched ones in the evidence report.
"""

from app.evidence.base import Evidence
from app.evidence.profiles import Profile
from app.evidence.rules import RuleContext
from app.evidence.types import (
    BrowserLogEvidence,
    BuildLogEvidence,
    HtmlEvidence,
    MobileDomEvidence,
    MobileScreenshotEvidence,
    TestLogEvidence,
    TestPropertiesEvidence,
    WebScreenshotEvidence,
)
from app.source.models import Attachment, RawScenario

_EVIDENCE_CLASSES: tuple[type[Evidence], ...] = (
    TestLogEvidence,
    TestPropertiesEvidence,
    BrowserLogEvidence,
    BuildLogEvidence,
    HtmlEvidence,
    MobileDomEvidence,
    WebScreenshotEvidence,
    MobileScreenshotEvidence,
)


def known_evidence_names() -> set[str]:
    """Every registered evidence name — what a profile may legally list.

    The wiring root validates profiles against this: a typo in
    `evidence_to_llm` would otherwise silently disable an evidence, and the
    config would read as if it were being sent.
    """
    return {cls.evidence_name for cls in _EVIDENCE_CLASSES}


def evidence_name_for(attachment: Attachment) -> str:
    """Evidence type this attachment maps to, or "" if none matches.

    Public because persistence also needs the mapping (to honour a profile's
    `evidence_to_store` when writing the raw evidence row).
    """
    for cls in _EVIDENCE_CLASSES:
        if cls.matches(attachment):
            return cls.evidence_name
    return ""


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
        context = ctx or RuleContext(scenario_name=scenario.scenario_name)
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
