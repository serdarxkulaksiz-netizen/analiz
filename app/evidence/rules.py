"""Content rules — per-evidence cutting/selecting, driven by profile config.

Each rule type is a small class implementing `apply(text, ctx) -> str`, chosen
from `RULE_REGISTRY` by its config `type`. A profile lists rules per evidence
name; the evidence applies them in order inside `select_content()`.

Adding a new rule type = one class + one registry row. Adding a new job's
behaviour = a config row only, no code.

Two ground rules:
  - Rules only shape what goes to the LLM. The full raw content is still
    written to `database/` (save-everything).
  - A rule that finds nothing leaves the text untouched — never silently
    empties the evidence.

HTML rules use the standard library's `html.parser` (no third-party
dependency): enough for "drop these tags with their subtree" and "take the
Nth <tag>". Compound CSS selectors would need a real parser — deliberately out
of scope for now.
"""

import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Any, ClassVar

from pydantic import BaseModel

# Tags that never have a closing tag; dropping them must not open a subtree.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class RuleContext(BaseModel):
    """Per-scenario context a rule may need (e.g. to find its own section)."""

    scenario_name: str = ""


class Rule(ABC):
    """One content-shaping step applied to a single evidence's text."""

    rule_type: ClassVar[str]

    @abstractmethod
    def apply(self, text: str, ctx: RuleContext) -> str:
        """Return the shaped text (or the input unchanged if not applicable)."""


# --- line/text rules ---------------------------------------------------------


class KeepScenarioSection(Rule):
    """Keep only this scenario's part of a job-level log.

    `start`/`end` are plain markers; `{scenario_name}` is substituted from the
    context. If the start marker is not found the text is left untouched.
    """

    rule_type = "keep_scenario_section"

    def __init__(self, start: str, end: str = "") -> None:
        self._start = start
        self._end = end

    def apply(self, text: str, ctx: RuleContext) -> str:
        start = self._start.format(scenario_name=ctx.scenario_name)
        index = text.find(start)
        if index == -1:
            return text
        rest = text[index:]
        if self._end:
            end = self._end.format(scenario_name=ctx.scenario_name)
            stop = rest.find(end, len(start))
            if stop != -1:
                return rest[:stop].rstrip()
        return rest


class KeepLastLines(Rule):
    """Keep the last N lines (logs put the failure at the end)."""

    rule_type = "keep_last_lines"

    def __init__(self, n: int) -> None:
        self._n = int(n)

    def apply(self, text: str, ctx: RuleContext) -> str:
        lines = text.splitlines()
        if len(lines) <= self._n:
            return text
        return "\n".join(lines[-self._n :])


class KeepFirstLines(Rule):
    """Keep the first N lines."""

    rule_type = "keep_first_lines"

    def __init__(self, n: int) -> None:
        self._n = int(n)

    def apply(self, text: str, ctx: RuleContext) -> str:
        lines = text.splitlines()
        if len(lines) <= self._n:
            return text
        return "\n".join(lines[: self._n])


class DropMatching(Rule):
    """Drop lines matching any of the given regex patterns (noise removal)."""

    rule_type = "drop_matching"

    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [re.compile(p) for p in patterns]

    def apply(self, text: str, ctx: RuleContext) -> str:
        kept = [
            line
            for line in text.splitlines()
            if not any(p.search(line) for p in self._patterns)
        ]
        return "\n".join(kept)


class KeepMatching(Rule):
    """Keep only lines matching any of the given regex patterns."""

    rule_type = "keep_matching"

    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [re.compile(p) for p in patterns]

    def apply(self, text: str, ctx: RuleContext) -> str:
        kept = [
            line
            for line in text.splitlines()
            if any(p.search(line) for p in self._patterns)
        ]
        return "\n".join(kept) if kept else text


class CollapseWhitespace(Rule):
    """Squeeze runs of whitespace (markup dumps are mostly indentation)."""

    rule_type = "collapse_whitespace"

    def apply(self, text: str, ctx: RuleContext) -> str:
        return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


class MaxChars(Rule):
    """Hard character cap — the last-resort size guard."""

    rule_type = "max_chars"

    def __init__(self, n: int) -> None:
        self._n = int(n)

    def apply(self, text: str, ctx: RuleContext) -> str:
        if len(text) <= self._n:
            return text
        return text[: self._n] + "\n…[kesildi]"


# --- markup rules (stdlib html.parser, no dependency) ------------------------


class _TagStripper(HTMLParser):
    """Re-emits markup, dropping the given tags together with their subtrees."""

    def __init__(self, drop_tags: set[str], drop_comments: bool) -> None:
        super().__init__(convert_charrefs=False)
        self._drop = drop_tags
        self._drop_comments = drop_comments
        self._depth = 0  # >0 while inside a dropped subtree
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
    """Drop the listed tags with everything inside them.

    Typical use: `{"type": "strip_tags", "tags": ["script", "style"]}` — this
    alone usually removes most of a DOM dump without losing structure.
    Include `"comment"` in `tags` to drop HTML comments as well.
    """

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


class _NthSelector(HTMLParser):
    """Captures the Nth element matching tag (+ optional class) with subtree."""

    def __init__(self, tag: str, class_name: str, index: int) -> None:
        super().__init__(convert_charrefs=False)
        self._tag = tag
        self._class = class_name
        self._index = index
        self._seen = -1
        self._depth = 0  # >0 while capturing the selected subtree
        self.out: list[str] = []

    def _matches(self, tag: str, attrs: Any) -> bool:
        if tag != self._tag:
            return False
        if not self._class:
            return True
        for name, value in attrs:
            if name == "class" and value:
                return self._class in value.split()
        return False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if self._depth:
            if tag == self._tag and tag not in _VOID_TAGS:
                self._depth += 1
            self.out.append(self.get_starttag_text() or f"<{tag}>")
            return
        if self.out:  # already captured the wanted element
            return
        if self._matches(tag, attrs):
            self._seen += 1
            if self._seen == self._index:
                self._depth = 1
                self.out.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        if self._depth:
            self.out.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        self.out.append(f"</{tag}>")
        if tag == self._tag:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self.out.append(data)

    def handle_comment(self, data: str) -> None:
        if self._depth:
            self.out.append(f"<!--{data}-->")


class SelectNth(Rule):
    """Keep only the Nth element of a given tag (0-based), with its subtree.

    Example: four `<LinearLayout>` blocks, take the first —
    `{"type": "select_nth", "match": {"tag": "LinearLayout"}, "index": 0}`.
    Tag names are matched case-insensitively (the parser lowercases them).
    If nothing matches, the text is left untouched.
    """

    rule_type = "select_nth"

    def __init__(self, match: dict[str, str], index: int = 0) -> None:
        self._tag = str(match.get("tag", "")).lower()
        self._class = str(match.get("class", ""))
        self._index = int(index)
        if not self._tag:
            raise ValueError("select_nth requires match.tag")

    def apply(self, text: str, ctx: RuleContext) -> str:
        parser = _NthSelector(self._tag, self._class, self._index)
        parser.feed(text)
        parser.close()
        selected = "".join(parser.out)
        return selected if selected.strip() else text


# --- registry ----------------------------------------------------------------

RULE_REGISTRY: dict[str, type[Rule]] = {
    rule.rule_type: rule
    for rule in (
        KeepScenarioSection,
        KeepLastLines,
        KeepFirstLines,
        DropMatching,
        KeepMatching,
        CollapseWhitespace,
        MaxChars,
        StripTags,
        SelectNth,
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
