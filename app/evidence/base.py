"""Evidence interface + two families.

This is the project's flexibility backbone. Each evidence:
  - declares what it matches: a `device_id` + file extension,
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
    """One piece of raw evidence for a scenario."""

    #: Registry key = class name (also used in profile config lists).
    evidence_name: ClassVar[str]
    #: Attachment identity this evidence matches: the device
    #: that produced it plus the file extension — the same pair VisiumGo's own
    #: UI shows as the attachment's name.
    device_id: ClassVar[str]
    extension: ClassVar[str]

    def __init__(self, *, goes_to_llm: bool) -> None:
        self.goes_to_llm = goes_to_llm

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

    def to_block(self) -> EvidenceBlock | None:
        """LLM-facing labeled block, or None when this evidence has none."""
        return None

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
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "Evidence":
        """Build this evidence from a matching attachment."""


class TextEvidence(Evidence):
    """Text evidence rendered as one `=== <dosya adı> · <ne olduğu> ===` block.

    The header names the file the way VisiumGo's UI names it, so a person and
    the model look at the same thing, and adds one short phrase saying what
    that file is — `browser.default.log` alone does not tell the model it is a
    browser console. The phrase is a property of the file type, so it lives on
    the class; the file name comes from the attachment, so a mobile block shows
    which device produced it.
    """

    #: What this file is, in one short phrase (Turkish, prompt-facing).
    description: ClassVar[str]

    def __init__(
        self,
        content: str,
        *,
        goes_to_llm: bool,
        file_label: str = "",
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> None:
        super().__init__(goes_to_llm=goes_to_llm)
        self._content = content or ""
        self._file_label = file_label
        self._rules = rules or []
        self._ctx = ctx or RuleContext()

    @property
    def block_label(self) -> str:
        """`<dosya adı> · <ne olduğu>` — the header this evidence renders under."""
        name = self._file_label or type(self).evidence_name
        return f"{name} · {type(self).description}" if type(self).description else name

    @property
    def _is_present(self) -> bool:
        """Did any text actually arrive? (Read only by `to_block`.)"""
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
        if self.goes_to_llm and self._is_present:
            return EvidenceBlock(
                label=self.block_label,
                content=self.select_content(),
                evidence_name=type(self).evidence_name,
            )
        return None

    @classmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "TextEvidence":
        return cls(
            attachment.content,
            goes_to_llm=goes_to_llm,
            file_label=attachment.label,
            rules=rules,
            ctx=ctx,
        )


class ScreenshotEvidence(Evidence):
    """Image evidence: recognised so it never enters the text prompt.

    Carries nothing. It used to carry the stored path, which the extractor
    collected into `Findings.screenshot_paths`, which the service wrote onto
    two different rows — three copies of a fact the attachment report already
    states once, per file, with its path.

    The class still earns its place: without it a `.png` would match no evidence
    at all, and an unmatched file is always downloaded and reported as "no class
    claimed this". Being recognised is the whole job.
    """

    @classmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        rules: list[Rule] | None = None,  # not applicable to binary evidence
        ctx: RuleContext | None = None,
    ) -> "ScreenshotEvidence":
        return cls(goes_to_llm=goes_to_llm)
