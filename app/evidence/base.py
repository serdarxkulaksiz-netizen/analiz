"""Evidence interface + two families (plan.md A5).

This is the project's flexibility backbone. Each evidence:
  - declares what it matches: a `device_id` + file extension (plan.md A5.1),
  - knows whether it goes to the LLM / to the store (flags from config, A5.2),
  - carries its own content selector — passthrough today (A5.3),
  - reports presence so missing evidence is tolerated, not fatal (A5.4),
  - builds itself from an Attachment (`from_attachment`) so no `if type ==`
    branching is needed anywhere (A0.1 / SOLID).

Two families avoid type-branching (SRP/OCP): text evidence produces a labeled
LLM block; screenshot evidence produces only a stored path (never sent to the
text LLM).
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.domain.findings import EvidenceBlock
from app.evidence.rules import Rule, RuleContext
from app.source.models import Attachment

__all__ = ["Evidence", "ScreenshotEvidence", "TextEvidence"]


class Evidence(ABC):
    """One piece of raw evidence for a scenario (plan.md A5.1)."""

    #: Registry key = class name (also used in profile config lists).
    evidence_name: ClassVar[str]
    #: Attachment identity this evidence matches (plan.md A5.1): the device
    #: that produced it plus the file extension — the same pair VisiumGo's own
    #: UI shows as the attachment's name.
    device_id: ClassVar[str]
    extension: ClassVar[str]

    def __init__(self, *, goes_to_llm: bool, goes_to_store: bool) -> None:
        self.goes_to_llm = goes_to_llm
        self.goes_to_store = goes_to_store

    @classmethod
    def matches(cls, attachment: Attachment) -> bool:
        """True if this evidence type handles the given attachment.

        `device_id` is matched exactly or by dotted prefix, so mobile files
        (`mobile.ios.iPhone 16`, `mobile.android.Samsung-M31`) all map through
        `device_id = "mobile"` — without any file-name `if`s.

        The extension, not the mime type, is the second half of the identity:
        `test.log` and `test.properties` arrive as `text/plain` from the same
        device, so a mime-based match cannot tell them apart (it used to put
        both into the step-flow block).
        """
        if attachment.extension != cls.extension:
            return False
        return attachment.device_id == cls.device_id or attachment.device_id.startswith(
            cls.device_id + "."
        )

    @property
    @abstractmethod
    def is_present(self) -> bool:
        """True if this evidence actually arrived (A5.4)."""

    def to_block(self) -> EvidenceBlock | None:
        """LLM-facing labeled block, or None (not present / not for LLM / no label)."""
        return None

    @property
    def screenshot_path(self) -> str:
        """Stored screenshot reference, or "" for non-screenshot evidence."""
        return ""

    @property
    def was_trimmed(self) -> bool:
        """True if content rules actually changed this evidence's content."""
        return False

    @classmethod
    @abstractmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        goes_to_store: bool,
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "Evidence":
        """Build this evidence from a matching attachment."""


class TextEvidence(Evidence):
    """Text evidence that renders as one labeled `=== <block_label> ===` block."""

    #: Findings evidence-block label this evidence fills (plan.md A6).
    block_label: ClassVar[str]

    def __init__(
        self,
        content: str,
        *,
        goes_to_llm: bool,
        goes_to_store: bool,
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> None:
        super().__init__(goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)
        self._content = content or ""
        self._rules = rules or []
        self._ctx = ctx or RuleContext()

    @property
    def is_present(self) -> bool:
        return bool(self._content.strip())

    def select_content(self) -> str:
        """Content selector (A5.3): applies the profile's rules, in order.

        With no rules this is passthrough. The raw content is untouched — only
        what reaches the LLM is shaped here.
        """
        text = self._content
        for rule in self._rules:
            text = rule.apply(text, self._ctx)
        return text

    @property
    def was_trimmed(self) -> bool:
        return bool(self._rules) and self.select_content() != self._content

    def to_block(self) -> EvidenceBlock | None:
        if self.goes_to_llm and self.is_present:
            return EvidenceBlock(label=self.block_label, content=self.select_content())
        return None

    @classmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        goes_to_store: bool,
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "TextEvidence":
        return cls(
            attachment.content,
            goes_to_llm=goes_to_llm,
            goes_to_store=goes_to_store,
            rules=rules,
            ctx=ctx,
        )


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

    @classmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        goes_to_store: bool,
        rules: list[Rule] | None = None,  # not applicable to binary evidence
        ctx: RuleContext | None = None,
    ) -> "ScreenshotEvidence":
        # A screenshot's reference is where it was actually written. A file the
        # profile never asked for has no path at all: pointing at a name that
        # was never downloaded would be worse than admitting it is not there.
        path = (
            "" if attachment.download_skipped else (attachment.stored_path or attachment.file_name)
        )
        return cls(path, goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)
