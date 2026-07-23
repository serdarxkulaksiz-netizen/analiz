"""Evidence architecture tests (plan.md A5): registry, flags, missing tolerance."""

from app.config import Settings
from app.domain.enums import Platform
from app.domain.findings import BLOCK_BROWSER, BLOCK_DOM, BLOCK_STEPS
from app.evidence.registry import EvidenceRegistry
from app.source.models import RawScenario


def _scenario(platform: Platform, **overrides: object) -> RawScenario:
    base = dict(
        scenario_name="S",
        platform=platform,
        test_log="STEP x | FAILED",
        dom_html="<html/>",
        browser_log="log",
        web_screenshot_path="w.png",
        mobile_screenshot_path="m.png",
    )
    base.update(overrides)
    return RawScenario(**base)  # type: ignore[arg-type]


def test_expected_evidence_per_platform(evidence_registry: EvidenceRegistry) -> None:
    web = {e.evidence_name for e in evidence_registry.build_for(_scenario(Platform.WEB))}
    mobile = {
        e.evidence_name for e in evidence_registry.build_for(_scenario(Platform.MOBILE))
    }
    hybrid = {
        e.evidence_name for e in evidence_registry.build_for(_scenario(Platform.HYBRID))
    }

    assert web == {
        "TestLogEvidence",
        "HtmlEvidence",
        "BrowserLogEvidence",
        "WebScreenshotEvidence",
    }
    assert mobile == {"TestLogEvidence", "MobileScreenshotEvidence"}
    assert hybrid == {
        "TestLogEvidence",
        "HtmlEvidence",
        "BrowserLogEvidence",
        "MobileScreenshotEvidence",
    }


def test_flags_control_llm_blocks(settings: Settings) -> None:
    # Screenshots never produce an LLM block; text evidence with goes_to_llm does.
    registry = EvidenceRegistry(settings.evidence_flags)
    by_name = {e.evidence_name: e for e in registry.build_for(_scenario(Platform.WEB))}

    assert by_name["TestLogEvidence"].to_block().label == BLOCK_STEPS
    assert by_name["HtmlEvidence"].to_block().label == BLOCK_DOM
    assert by_name["BrowserLogEvidence"].to_block().label == BLOCK_BROWSER
    assert by_name["WebScreenshotEvidence"].to_block() is None
    assert by_name["WebScreenshotEvidence"].screenshot_path == "w.png"


def test_flag_override_stops_evidence_going_to_llm(settings: Settings) -> None:
    flags = {**settings.evidence_flags}
    flags["BrowserLogEvidence"] = {"goes_to_llm": False, "goes_to_store": True}
    registry = EvidenceRegistry(flags)
    by_name = {e.evidence_name: e for e in registry.build_for(_scenario(Platform.WEB))}

    # Config-only change: browser log no longer goes to the LLM.
    assert by_name["BrowserLogEvidence"].to_block() is None


def test_missing_evidence_is_present_false(evidence_registry: EvidenceRegistry) -> None:
    evidences = evidence_registry.build_for(_scenario(Platform.WEB, dom_html=""))
    html = next(e for e in evidences if e.evidence_name == "HtmlEvidence")
    assert html.is_missing is True
    assert html.to_block() is None
