"""Evidence registry (plan.md A4.2 / A5).

Maps evidence names to classes, and each platform to its expected evidence
set. Building evidence for a scenario goes through here, so there is no
`if platform ==` anywhere: the expected set is a registry lookup, and adding a
platform (or splitting mobile into android/ios later) is a new row here, not a
code change upstream (A4.2).

The platform → evidence-types map is architectural structure (which files a
platform produces), so it lives in the registry — not a tunable business value.
The per-evidence `goes_to_llm`/`goes_to_store` flags ARE tunable and come from
config (A5.2), injected here.
"""

from app.domain.enums import Platform
from app.evidence.base import Evidence
from app.evidence.types import (
    BrowserLogEvidence,
    HtmlEvidence,
    MobileScreenshotEvidence,
    TestLogEvidence,
    WebScreenshotEvidence,
)
from app.source.models import RawScenario

_EVIDENCE_CLASSES: tuple[type[Evidence], ...] = (
    TestLogEvidence,
    HtmlEvidence,
    BrowserLogEvidence,
    WebScreenshotEvidence,
    MobileScreenshotEvidence,
)

# Expected evidence per platform (plan.md A4.3). Adding a platform = one row.
_DEFAULT_PLATFORM_EVIDENCE: dict[Platform, list[str]] = {
    Platform.WEB: [
        "TestLogEvidence",
        "HtmlEvidence",
        "BrowserLogEvidence",
        "WebScreenshotEvidence",
    ],
    Platform.MOBILE: [
        "TestLogEvidence",
        "MobileScreenshotEvidence",
    ],
    Platform.HYBRID: [
        "TestLogEvidence",
        "HtmlEvidence",
        "BrowserLogEvidence",
        "MobileScreenshotEvidence",
    ],
}


class EvidenceRegistry:
    """Builds the expected evidence instances for a scenario's platform."""

    def __init__(
        self,
        evidence_flags: dict[str, dict[str, bool]],
        platform_evidence: dict[Platform, list[str]] | None = None,
    ) -> None:
        self._classes = {cls.evidence_name: cls for cls in _EVIDENCE_CLASSES}
        self._flags = evidence_flags
        self._platform_evidence = platform_evidence or _DEFAULT_PLATFORM_EVIDENCE

    def build_for(self, scenario: RawScenario) -> list[Evidence]:
        """Return one Evidence instance per expected type for this platform.

        Instances are always built (even when the underlying field is empty),
        so a missing file surfaces as `evidence.is_missing` rather than being
        silently skipped (A5.4).
        """
        names = self._platform_evidence.get(scenario.platform, [])
        evidences: list[Evidence] = []
        for name in names:
            cls = self._classes[name]
            flags = self._flags.get(name, {"goes_to_llm": True, "goes_to_store": True})
            evidences.append(
                cls.from_scenario(
                    scenario,
                    goes_to_llm=flags.get("goes_to_llm", True),
                    goes_to_store=flags.get("goes_to_store", True),
                )
            )
        return evidences
