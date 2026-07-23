"""The five evidence classes (plan.md A5.1 — only these).

Each maps one raw file to its natural block/path. There is NO separate mobile
XML/DOM evidence: the mobile UI tree arrives inside `test.log`, carried as-is
by `TestLogEvidence` (plan.md A4.3).

The `=== HATA ===` and `=== CONSOLE.LOG ===` blocks are NOT evidence classes:
HATA is the minimally-identified `error_message` (an A6 field already), and
CONSOLE.LOG is the job-level Jenkins log — both assembled by the extractor.
"""

from app.domain.findings import BLOCK_BROWSER, BLOCK_DOM, BLOCK_STEPS
from app.evidence.base import ScreenshotEvidence, TextEvidence
from app.source.models import RawScenario


class TestLogEvidence(TextEvidence):
    """`test.log` — the time-ordered step-flow backbone → `=== ADIMLAR ===`."""

    evidence_name = "TestLogEvidence"
    block_label = BLOCK_STEPS

    @classmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "TestLogEvidence":
        return cls(scenario.test_log, goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)


class HtmlEvidence(TextEvidence):
    """`browser.default.html` — the page DOM → `=== DOM ===`."""

    evidence_name = "HtmlEvidence"
    block_label = BLOCK_DOM

    @classmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "HtmlEvidence":
        return cls(scenario.dom_html, goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)


class BrowserLogEvidence(TextEvidence):
    """`browser.default.log` — the browser log → `=== BROWSER LOG ===`."""

    evidence_name = "BrowserLogEvidence"
    block_label = BLOCK_BROWSER

    @classmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "BrowserLogEvidence":
        return cls(scenario.browser_log, goes_to_llm=goes_to_llm, goes_to_store=goes_to_store)


class WebScreenshotEvidence(ScreenshotEvidence):
    """`browser.default.png` — stored reference only."""

    evidence_name = "WebScreenshotEvidence"

    @classmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "WebScreenshotEvidence":
        return cls(
            scenario.web_screenshot_path,
            goes_to_llm=goes_to_llm,
            goes_to_store=goes_to_store,
        )


class MobileScreenshotEvidence(ScreenshotEvidence):
    """`mobile.{os}.{brand}.png` — stored reference only (path not used to route)."""

    evidence_name = "MobileScreenshotEvidence"

    @classmethod
    def from_scenario(
        cls, scenario: RawScenario, *, goes_to_llm: bool, goes_to_store: bool
    ) -> "MobileScreenshotEvidence":
        return cls(
            scenario.mobile_screenshot_path,
            goes_to_llm=goes_to_llm,
            goes_to_store=goes_to_store,
        )
