"""Content rules — per-evidence cutting/selecting, driven by profile config."""

import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class RuleContext(BaseModel):
    """Per-scenario context a rule may need (e.g. to find its own section)."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str = ""


class RuleError(ValueError):
    """A content rule could not do what the profile asked it to do."""


class Rule(ABC):
    """One content-shaping step applied to a single evidence's text."""

    rule_type: ClassVar[str]

    @abstractmethod
    def apply(self, text: str, ctx: RuleContext) -> str:
        """Return the shaped text (or the input unchanged if not applicable)."""


class KeepScenarioSection(Rule):
    """Keep only this scenario's part of a job-level log."""

    rule_type = "keep_scenario_section"

    DEFAULT_START = "> Scenario [{scenario_name}] started"
    DEFAULT_END = "> Scenario ["

    def __init__(self, start: str | None = None, end: str | None = None) -> None:
        self._start = start if start else self.DEFAULT_START
        self._end = self.DEFAULT_END if end is None else end

    def apply(self, text: str, ctx: RuleContext) -> str:
        start = self._start.format(scenario_name=ctx.scenario_name)
        index = text.find(start)
        if index == -1:
            raise RuleError(
                f"{self.rule_type}: başlangıç işareti bulunamadı ({start!r}). "
                f"Log {len(text)} karakter; bu senaryonun bölümü ayrılamadı."
            )
        rest = text[index:]
        if self._end:
            end = self._end.format(scenario_name=ctx.scenario_name)
            stop = rest.find(end, len(start))
            if stop != -1:
                line_start = rest.rfind("\n", 0, stop)
                if line_start != -1:
                    stop = line_start
                return rest[:stop].rstrip()
        return rest


class CollapseWhitespace(Rule):
    """Squeeze runs of whitespace (markup dumps are mostly indentation)."""

    rule_type = "collapse_whitespace"

    def apply(self, text: str, ctx: RuleContext) -> str:
        text = re.sub(r"(?m)^[ \t]+$", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return re.sub(r"[ \t]{2,}", " ", text).strip()


class _TagStripper(HTMLParser):
    """Re-emits markup, dropping the given tags together with their subtrees."""

    def __init__(self, drop_tags: set[str], drop_comments: bool) -> None:
        super().__init__(convert_charrefs=False)
        self._drop = drop_tags
        self._drop_comments = drop_comments
        self._depth = 0
        self.out: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._drop:
            if tag not in _VOID_TAGS:
                self._depth += 1
            return
        if not self._depth:
            self.out.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        if tag in self._drop or self._depth:
            return
        self.out.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._drop and tag not in _VOID_TAGS:
            if self._depth:
                self._depth -= 1
            return
        if not self._depth:
            self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._depth:
            self.out.append(data)

    def handle_comment(self, data: str) -> None:
        if not self._depth and not self._drop_comments:
            self.out.append(f"<!--{data}-->")

    def handle_entityref(self, name: str) -> None:
        if not self._depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._depth:
            self.out.append(f"&#{name};")


class StripTags(Rule):
    """Drop the listed tags with everything inside them."""

    rule_type = "strip_tags"

    def __init__(self, tags: list[str]) -> None:
        lowered = {t.lower() for t in tags}
        self._drop_comments = "comment" in lowered
        self._tags = lowered - {"comment"}

    def apply(self, text: str, ctx: RuleContext) -> str:
        parser = _TagStripper(self._tags, self._drop_comments)
        parser.feed(text)
        parser.close()
        return "".join(parser.out)


RULE_REGISTRY: dict[str, type[Rule]] = {
    rule.rule_type: rule
    for rule in (
        KeepScenarioSection,
        CollapseWhitespace,
        StripTags,
    )
}


def build_rule(config: dict[str, Any]) -> Rule:
    """Build one rule from its config dict; raises on bad config (fail fast)."""
    params = dict(config)
    rule_type = params.pop("type", "")
    cls = RULE_REGISTRY.get(rule_type)
    if cls is None:
        known = ", ".join(sorted(RULE_REGISTRY))
        raise ValueError(f"Unknown rule type {rule_type!r}. Known: {known}")
    try:
        return cls(**params)
    except (TypeError, ValueError, re.error) as exc:
        raise ValueError(f"Invalid config for rule {rule_type!r}: {exc}") from exc
