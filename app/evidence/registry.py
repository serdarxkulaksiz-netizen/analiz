"""Evidence registry."""

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
    """Every registered evidence name — what a profile may legally list."""
    return {cls.evidence_name for cls in _EVIDENCE_CLASSES}


def evidence_name_for(attachment: Attachment) -> str:
    """Evidence type this attachment maps to, or "" if none matches."""
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

    def build_job_log(
        self,
        build_log: str,
        profile: Profile,
        ctx: RuleContext | None = None,
    ) -> Evidence | None:
        """Build the job-level build log evidence — WITHOUT faking an attachment."""
        if not build_log:
            return None
        name = BuildLogEvidence.evidence_name
        return BuildLogEvidence(
            build_log,
            goes_to_llm=name in profile.evidence_to_llm,
            file_label=f"{BuildLogEvidence.device_id}{BuildLogEvidence.extension}",
            rules=profile.rules_for(name),
            ctx=ctx,
        )

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
                    rules=profile.rules_for(cls.evidence_name),
                    ctx=context,
                )
            )
        return evidences
