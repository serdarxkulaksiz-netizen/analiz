"""Evidence interface + two families (plan.md A5).

This is the project's flexibility backbone. Each evidence:
  - knows whether it goes to the LLM / to the store (flags from config, A5.2),
  - carries its own content selector — passthrough today (A5.3),
  - reports presence so missing evidence is tolerated, not fatal (A5.4),
  - builds itself from a RawScenario (`from_scenario`) so no `if type ==`
    branching is needed anywhere (A0.1 / SOLID).

Two families avoid type-branching (SRP/OCP): text evidence produces a labeled
LLM block; screenshot evidence produces only a stored path (never sent to the
text LLM).
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.domain.findings import EvidenceBlock
from app.source.models import RawScenario


class Evidence(ABC):
    """One piece of raw evidence for a scenario (plan.md A5.1)."""

    #: Registry key = class name; also the label used in `missing_evidence`.
    evidence_name: ClassVar[str]

    def __init__(self, *, goes_to_llm: bool, goes_to_store: bool) -> None:
        self.goes_to_llm = goes_to_llm
        self.goes_to_store = goes_to_store

    @property
    @abstractmethod
    def is_present(self) -> bool:
        """True if this evidence actually arrived (A5.4)."""

    @property
    def is_missing(self) -> bool:
        return not self.is_present

    def to_block(self) -> EvidenceBlock | None:
        """LLM-facing labeled block, or None (not present / not for LLM / no label)."""
        return None

    @property
    def screenshot_path(self) -> str:
        """Stored screenshot reference, or "" for non-screenshot evidence."""
        return ""

    @classmethod
    @abstractmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "Evidence":
        """Build this evidence from its own field of the raw scenario."""


class TextEvidence(Evidence):
    """Text evidence that renders as one labeled `=== <block_label> ===` block."""

    #: Findings evidence-block label this evidence fills (plan.md A6).
    block_label: ClassVar[str]

    def __init__(self, content: str, *, goes_to_llm: bool, goes_to_store: bool) -> None:
        super().__init__(goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)
        self._content = content or ""

    @property
    def is_present(self) -> bool:
        return bool(self._content.strip())

    def select_content(self) -> str:
        """Content selector (A5.3): passthrough today — nothing is cut."""
        return self._content

    def to_block(self) -> EvidenceBlock | None:
        if self.goes_to_llm and self.is_present:
            return EvidenceBlock(label=self.block_label, content=self.select_content())
        return None


class ScreenshotEvidence(Evidence):
    """Screenshot evidence: a stored path only; never sent to the text LLM."""

    def __init__(self, path: str, *, goes_to_llm: bool, goes_to_store: bool) -> None:
        super().__init__(goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)
        self._path = path or ""

    @property
    def is_present(self) -> bool:
        return bool(self._path)

    @property
    def screenshot_path(self) -> str:
        return self._path
