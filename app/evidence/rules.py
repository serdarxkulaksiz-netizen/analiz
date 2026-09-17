"""Content rules — per-evidence cutting/selecting, driven by profile config.

Each rule type is a small class implementing `apply(text, ctx) -> str`, chosen
from `RULE_REGISTRY` by its config `type`. A profile lists rules per evidence
name; the evidence applies them in order inside `select_content()`.

Adding a new rule type = one class + one registry row. Adding a new job's
behaviour = a config row only, no code.

Two ground rules:
  - Rules only shape what goes to the LLM. The full raw content is still
    written to `database/` (save-everything).
  - A rule that cannot do what it was asked RAISES (`RuleError`). It does not
    quietly return the input: "I could not slice this" and "here is the whole
    thing" are different answers, and the config only asked for one of them.

The markup rule uses the standard library's `html.parser` (no third-party
dependency): enough for "drop these tags with their subtree". Anything that
needs real selectors would need a real parser — deliberately out of scope.

There are three rules, and each one is used by a profile today. Six others
shipped with this engine on day one — line pickers, pattern filters, a size
cap, an Nth-element selector — written for job shapes that had not been seen
yet. None was ever referenced by `profiles.json`, so they were removed: a rule
nobody runs is a rule nobody notices is wrong (one of them repeated, unseen,
the same silent-fallback bug that had to be fixed in `keep_scenario_section`).
Adding one back is a class and a registry row.
"""

import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

# Tags that never have a closing tag; dropping them must not open a subtree.
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
    """Per-scenario context a rule may need (e.g. to find its own section).

    `extra="forbid"` on purpose: passing a field that does not exist here used
    to be swallowed silently, so the value never reached any rule and nothing
    complained. Now it fails loudly at the call site.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_name: str = ""


class RuleError(ValueError):
    """A content rule could not do what the profile asked it to do.

    Raised instead of quietly returning the input unchanged. A rule that says
    "keep only this scenario's section" and cannot find that section has not
    trimmed anything — it has failed, and passing the whole job log through as
    if nothing happened sends every scenario the same megabyte of unrelated
    output while the config reads as if it were sliced.
    """


class Rule(ABC):
    """One content-shaping step applied to a single evidence's text."""

    rule_type: ClassVar[str]

    @abstractmethod
    def apply(self, text: str, ctx: RuleContext) -> str:
        """Return the shaped text (or the input unchanged if not applicable)."""


# --- line/text rules ---------------------------------------------------------


class KeepScenarioSection(Rule):
    """Keep only this scenario's part of a job-level log.

    The markers are a property of the **log format**, not a per-job decision, so
    they live here as defaults rather than being repeated in every profile:
    VisiumGo's build.log opens each scenario with
    `beforeScenario:63 - [2]  > Scenario [<ad>] started`, and the NEXT
    scenario's opening line is where that scenario's part ends. The end marker
    used to be `beforeScenario:`, which also matches lines INSIDE the same
    scenario (`beforeScenario:50 - Scenario source tag:` follows the opening
    line immediately), so every section was cut after ~2 lines and the whole
    body — steps, failure, stack trace — was dropped. Config only has to ask
    for the rule:

        {"type": "keep_scenario_section"}

    A job whose log looks different can still override either marker (and
    `"end": ""` means "keep to the end of the file"). `{scenario_name}` is
    substituted from the context.

    If the start marker is NOT found, this raises `RuleError`. It used to
    return the whole log instead, which looked harmless and was not: every
    scenario of the run then carried the entire job log — measured at 38.889
    characters × 40 scenarios — while `profiles.json` still read "sliced per
    scenario". A marker that does not match is a fact about the log format that
    somebody has to see, not a case to shrug off.
    """

    rule_type = "keep_scenario_section"

    #: VisiumGo build.log scenario boundary (verified against a real log).
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
                # `stop` lands mid-line on the NEXT scenario's opening line (it
                # is preceded by that line's timestamp and `beforeScenario:NN`).
                # Cut at that line's start so no fragment of the next scenario
                # dangles at the end of this one's section.
                line_start = rest.rfind("\n", 0, stop)
                if line_start != -1:
                    stop = line_start
                return rest[:stop].rstrip()
        return rest


class CollapseWhitespace(Rule):
    """Squeeze runs of whitespace (markup dumps are mostly indentation).

    Three passes, and the order is the point:

    1. A line holding nothing but spaces becomes empty. This is what the rule
       used to miss: `strip_tags` removes a tag and leaves its indentation
       behind ("    \n    \n"), and those lines are not consecutive newlines,
       so the blank-run pass below could not see them. They survived as lines
       containing one space — holes that still cost tokens.
    2. Three or more newlines become one blank line.
    3. Runs of spaces/tabs become one space.
    """

    rule_type = "collapse_whitespace"

    def apply(self, text: str, ctx: RuleContext) -> str:
        text = re.sub(r"(?m)^[ \t]+$", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return re.sub(r"[ \t]{2,}", " ", text).strip()


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


# --- registry ----------------------------------------------------------------

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
