"""Evidence interface + two families."""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.domain.findings import EvidenceBlock
from app.evidence.rules import Rule, RuleContext
from app.source.models import Attachment

__all__ = ["Evidence", "ScreenshotEvidence", "TextEvidence"]


class Evidence(ABC):
    """One piece of raw evidence for a scenario."""

    evidence_name: ClassVar[str]
    device_id: ClassVar[str]
    extension: ClassVar[str]

    def __init__(self, *, goes_to_llm: bool) -> None:
        self.goes_to_llm = goes_to_llm

    @classmethod
    def matches(cls, attachment: Attachment) -> bool:
        """True if this evidence type handles the given attachment."""
        if attachment.extension != cls.extension:
            return False
        return attachment.device_id == cls.device_id or attachment.device_id.startswith(
            cls.device_id + "."
        )

    def to_block(self) -> EvidenceBlock | None:
        """LLM-facing labeled block, or None when this evidence has none."""
        return None

    @classmethod
    @abstractmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        description: str = "",
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "Evidence":
        """Build this evidence from a matching attachment."""


class TextEvidence(Evidence):
    """Text evidence rendered as one `=== <dosya adı> · <ne olduğu> ===` block."""

    description: ClassVar[str]

    def __init__(
        self,
        content: str,
        *,
        goes_to_llm: bool,
        file_label: str = "",
        description: str = "",
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> None:
        super().__init__(goes_to_llm=goes_to_llm)
        self._content = content or ""
        self._file_label = file_label
        self._description = description
        self._rules = rules or []
        self._ctx = ctx or RuleContext()
        self._selected: str | None = None

    @property
    def block_label(self) -> str:
        """The file name this evidence renders under."""
        return self._file_label or type(self).evidence_name

    @property
    def block_description(self) -> str:
        """What this evidence is, in one sentence, for the prompt.

        The profile may override it: one evidence class can carry two different
        things — `finart` sends one scenario's slice of the build log, `error`
        sends the whole run's — and a single sentence would lie to one of them.
        """
        return self._description or type(self).description

    @property
    def raw_content(self) -> str:
        """The text exactly as it arrived, before any content rule touched it.

        What a check must search: the shaped version has had attributes and
        sections removed, so "not found" there can mean "we removed it".
        """
        return self._content

    @property
    def _is_present(self) -> bool:
        """Did any text actually arrive? (Read only by `to_block`.)"""
        return bool(self._content.strip())

    def select_content(self) -> str:
        """Content selector: applies the profile's rules, in order (once).

        The result is kept: a whole job log run through the rules twice per
        scenario is work nobody reads.
        """
        if self._selected is None:
            text = self._content
            for rule in self._rules:
                text = rule.apply(text, self._ctx)
            self._selected = text
        return self._selected

    def to_block(self) -> EvidenceBlock | None:
        if self.goes_to_llm and self._is_present:
            return EvidenceBlock(
                label=self.block_label,
                description=self.block_description,
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
        description: str = "",
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "TextEvidence":
        return cls(
            attachment.content,
            goes_to_llm=goes_to_llm,
            file_label=attachment.label,
            description=description,
            rules=rules,
            ctx=ctx,
        )


class ScreenshotEvidence(Evidence):
    """Image evidence: recognised so it never enters the text prompt."""

    @classmethod
    def from_attachment(
        cls,
        attachment: Attachment,
        *,
        goes_to_llm: bool,
        description: str = "",
        rules: list[Rule] | None = None,
        ctx: RuleContext | None = None,
    ) -> "ScreenshotEvidence":
        return cls(goes_to_llm=goes_to_llm)
