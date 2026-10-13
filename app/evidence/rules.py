"""Content rules — per-evidence cutting/selecting, driven by profile config."""

import re
from abc import ABC, abstractmethod
from html import escape
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
    """Keep only this scenario's part of a job-level log.

    The section is located by the scenario's NAME, which is the only thing the
    log gives us — and a name is not an identity: two examples of one Scenario
    Outline open two sections under the same name. Then there is no way to tell
    which one belongs to the scenario being analyzed, so nothing is cut and the
    rule says so. Sending the first section to both would hand one scenario
    another one's log, quietly, and that is the one thing this rule exists to
    prevent.
    """

    rule_type = "keep_scenario_section"

    DEFAULT_START = "> Scenario [{scenario_name}] started"
    DEFAULT_END = "> Scenario ["

    def __init__(self, start: str | None = None, end: str | None = None) -> None:
        self._start = start if start else self.DEFAULT_START
        self._end = self.DEFAULT_END if end is None else end

    def apply(self, text: str, ctx: RuleContext) -> str:
        # TODO: the LAST scenario has no next opening line, so its section runs
        # to the end of the file and swallows the run-level tail — the runner's
        # `Failed scenarios:` list (which names OTHER scenarios), the build
        # tool's summary, the post-build output. Reproduced: five scenarios cut
        # clean, the sixth carried three foreign scenario names. The fix needs
        # `end` to accept several markers ("whichever comes first"), and the
        # markers have to be read off a sample build.log, not guessed.
        start = self._start.format(scenario_name=ctx.scenario_name)
        index = text.find(start)
        if index == -1:
            raise RuleError(
                f"{self.rule_type}: başlangıç işareti bulunamadı ({start!r}). "
                f"Log {len(text)} karakter; bu senaryonun bölümü ayrılamadı."
            )
        found = text.count(start)
        if found > 1:
            raise RuleError(
                f"{self.rule_type}: aynı başlangıç işaretiyle {found} bölüm var "
                f"({start!r}). Hangisinin bu senaryoya ait olduğu logdan "
                "belirlenemiyor; başka bir senaryonun logunu göndermemek için kesilmedi."
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


class _AttributeFilter(HTMLParser):
    """Re-emits markup, keeping only the attributes it was told to keep.

    The value is escaped on the way out because the parser hands it over
    DECODED: `title="Tutar &quot;TL&quot;"` arrives as `Tutar "TL"`, and writing
    that back raw closes the attribute in the middle and breaks the tag.
    """

    def __init__(self, keep: set[str], keep_prefixes: tuple[str, ...]) -> None:
        super().__init__(convert_charrefs=False)
        self._keep = keep
        self._prefixes = keep_prefixes
        self.out: list[str] = []

    def _wanted(self, name: str) -> bool:
        return name in self._keep or name.startswith(self._prefixes)

    def _tag(self, tag: str, attrs: Any, closing: str) -> str:
        parts = [tag]
        for name, value in attrs:
            if not self._wanted(name.lower()):
                continue
            parts.append(name if value is None else f'{name}="{escape(value, quote=True)}"')
        return f"<{' '.join(parts)}{closing}>"

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.out.append(self._tag(tag, attrs, ""))

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        self.out.append(self._tag(tag, attrs, "/"))

    def handle_endtag(self, tag: str) -> None:
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.out.append(data)

    def handle_comment(self, data: str) -> None:
        self.out.append(f"<!--{data}-->")

    def handle_entityref(self, name: str) -> None:
        self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.out.append(f"&#{name};")


class KeepAttributes(Rule):
    """Drop every HTML attribute except the ones a diagnosis actually reads.

    A modern app's DOM is mostly attributes, not text: framework markers
    (`_ngcontent-*`), inline styles, analytics hooks, generated ids. Measured on
    a realistic page, `strip_tags` + `collapse_whitespace` removed 8% and 93% of
    what remained was attributes.

    What is KEPT is what a failure is diagnosed with: the locator surface
    (`id`, `class`, `name`, `type`, `value`, `for`, `href`), what the user would
    see (`title`, `alt`, `placeholder`), the native state (`disabled`, `hidden`,
    `checked`, `selected`, `readonly`, `required`, `open`, `inert`), the test
    hooks (`data-test*`, `data-qa*`, `data-cy*`) and EVERY `aria-*`.

    All of ARIA is kept on purpose: those attributes are the page's own account
    of what a person would perceive, which is the question a failed interaction
    asks. Dropping them does not merely lose detail, it MISLEADS — an
    `aria-hidden="true"` dialog reads as present and visible once the attribute
    is gone, and the diagnosis becomes "the element was there, so the locator is
    fine". Component libraries carry the same state in `data-state` and
    `data-disabled`, so those two are kept by name.

    `keep` is overridable from config; a name ending in `*` matches by prefix.
    """

    rule_type = "keep_attributes"

    DEFAULT_KEEP = (
        "id",
        "class",
        "name",
        "type",
        "value",
        "href",
        "src",
        "for",
        "role",
        "title",
        "alt",
        "placeholder",
        "label",
        "disabled",
        "hidden",
        "checked",
        "selected",
        "readonly",
        "required",
        "open",
        "inert",
        "aria-*",
        "data-state",
        "data-disabled",
        "data-test*",
        "data-qa*",
        "data-cy*",
    )

    def __init__(self, keep: list[str] | None = None) -> None:
        names = list(keep) if keep else list(self.DEFAULT_KEEP)
        if not names:
            raise ValueError("keep must not be empty")
        self._exact = {n.lower() for n in names if not n.endswith("*")}
        self._prefixes = tuple(n.lower()[:-1] for n in names if n.endswith("*"))

    def apply(self, text: str, ctx: RuleContext) -> str:
        parser = _AttributeFilter(self._exact, self._prefixes)
        parser.feed(text)
        parser.close()
        return "".join(parser.out)


class StripBase64(Rule):
    """Replace long base64 runs with a note saying how much was dropped.

    A DOM carries images as `data:` URIs and a test log carries documents as
    base64 fields; both are thousands of characters that mean nothing to a
    reader. The run is replaced, not deleted: an EMPTY or unexpectedly small
    payload is itself a finding, and the note keeps that visible.

    Matched by shape, not by field name, so a new field carrying base64 is
    covered without anyone editing a list. `min_chars` sets how long a run has
    to be; below it, nothing is touched. At the default, a long JWT's payload
    segment is replaced too — it is a token, not something a diagnosis reads.
    Measured at this threshold with no false positive on URLs, feature paths,
    xpath and CSS selectors, 64-character hex ids, Java stack frames, Android
    resource ids or HTTP status lines.
    """

    rule_type = "strip_base64"

    def __init__(self, min_chars: int = 100) -> None:
        if min_chars <= 0:
            raise ValueError("min_chars must be greater than 0")
        self._pattern = re.compile(rf"[A-Za-z0-9+/]{{{min_chars},}}={{0,2}}")

    def apply(self, text: str, ctx: RuleContext) -> str:
        return self._pattern.sub(lambda m: f"[base64 {len(m.group(0))} karakter]", text)


class StripTags(Rule):
    """Drop the listed tags with everything inside them."""

    rule_type = "strip_tags"

    def __init__(self, tags: list[str]) -> None:
        lowered = {t.lower() for t in tags}
        self._drop_comments = "comment" in lowered
        self._tags = lowered - {"comment"}

    def apply(self, text: str, ctx: RuleContext) -> str:
        # TODO: this is an HTML parser, and it lower-cases closing tags:
        # `<ScrollView>...</ScrollView>` comes back as `<ScrollView>...</scrollview>`.
        # Harmless for HTML, wrong for the mobile UI tree, which is XML and
        # case-sensitive. No profile sends XML through this rule today; one that
        # does needs a case-preserving path first.
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
        KeepAttributes,
        StripBase64,
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
