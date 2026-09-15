"""Evidence registry / real-spec Bölüm 3).

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

    def build_job_log(
        self,
        build_log: str,
        profile: Profile,
        ctx: RuleContext | None = None,
    ) -> Evidence | None:
        """Build the job-level build log evidence — WITHOUT faking an attachment.

        The build log comes from `/api/runs/{run_id}/logs`, not from a
        scenario's `attachments[]`. It used to be wrapped in a synthetic
        `Attachment` so it could ride the normal mapping; that made the
        evidence report claim VisiumGo had sent a file it never sent. The
        evidence is built straight from the text instead: profile flags and
        content rules apply exactly as they do for every other evidence.

        Returns None when there is no log — the caller has nothing to add.
        """
        if not build_log:
            return None
        name = BuildLogEvidence.evidence_name
        return BuildLogEvidence(
            build_log,
            goes_to_llm=name in profile.evidence_to_llm,
            goes_to_store=name in profile.evidence_to_store,
            # The name VisiumGo's own UI shows for this file, so the prompt
            # header reads the same as every attachment-backed block.
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
                    goes_to_store=cls.evidence_name in profile.evidence_to_store,
                    rules=profile.rules_for(cls.evidence_name),
                    ctx=context,
                )
            )
        return evidences
