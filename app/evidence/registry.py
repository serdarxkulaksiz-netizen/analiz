"""Evidence registry (plan.md A4.2 / A5 / real-spec Bölüm 3).

Maps attachments to Evidence classes by `(mime_type, device_id)` — no file-name
`if`s (real-spec Bölüm 3). Also holds each platform's expected evidence set, so
missing evidence is detected without any `if platform ==`: adding a platform
(or splitting mobile into android/ios later) is a new row here, not a code
change upstream (A4.2).

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
from app.source.models import Attachment, RawScenario

_EVIDENCE_CLASSES: tuple[type[Evidence], ...] = (
    TestLogEvidence,
    BrowserLogEvidence,
    HtmlEvidence,
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
    """Maps attachments to Evidence and reports the expected set per platform."""

    def __init__(
        self,
        evidence_flags: dict[str, dict[str, bool]],
        platform_evidence: dict[Platform, list[str]] | None = None,
    ) -> None:
        self._classes = {cls.evidence_name: cls for cls in _EVIDENCE_CLASSES}
        self._flags = evidence_flags
        self._platform_evidence = platform_evidence or _DEFAULT_PLATFORM_EVIDENCE

    def _flags_for(self, name: str) -> dict[str, bool]:
        return self._flags.get(name, {"goes_to_llm": True, "goes_to_store": True})

    def _class_for(self, attachment: Attachment) -> type[Evidence] | None:
        for cls in _EVIDENCE_CLASSES:
            if cls.matches(attachment):
                return cls
        return None

    def build_for(self, scenario: RawScenario) -> list[Evidence]:
        """Build one Evidence per attachment that maps to a known class.

        Attachments with no matching class are skipped (unknown type). Presence
        is per-Evidence (`is_present`); missing expected evidence is reported by
        `missing_names`, not by silently dropping (A5.4).
        """
        evidences: list[Evidence] = []
        for attachment in scenario.attachments:
            cls = self._class_for(attachment)
            if cls is None:
                continue
            flags = self._flags_for(cls.evidence_name)
            evidences.append(
                cls.from_attachment(
                    attachment,
                    goes_to_llm=flags.get("goes_to_llm", True),
                    goes_to_store=flags.get("goes_to_store", True),
                )
            )
        return evidences

    def expected_names(self, platform: Platform) -> list[str]:
        """Evidence types expected for this platform (for missing detection)."""
        return list(self._platform_evidence.get(platform, []))

    def missing_names(
        self, platform: Platform, present: list[Evidence]
    ) -> list[str]:
        """Expected-but-absent evidence types (A5.4).

        An expected type counts as present only if at least one built evidence
        of that type actually arrived (`is_present`).
        """
        present_ok = {
            type(evidence).evidence_name
            for evidence in present
            if evidence.is_present
        }
        return [
            name
            for name in self.expected_names(platform)
            if name not in present_ok
        ]
