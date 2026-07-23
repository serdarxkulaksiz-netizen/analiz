"""MockExtractor tests: Evidence architecture -> Findings (plan.md A5, A6)."""

from app.domain.enums import Platform, StepStatus
from app.domain.findings import (
    BLOCK_BROWSER,
    BLOCK_DOM,
    BLOCK_ERROR,
    BLOCK_STEPS,
    Findings,
)
from app.extraction.mock import MockExtractor
from app.source.models import RawScenario

_TEST_LOG = """2026-07-16 10:00:01 STEP Adım bir | PASSED
2026-07-16 10:00:07 STEP Adım iki | FAILED
2026-07-16 10:00:07 ERROR NoSuchElementException: #btn
2026-07-16 10:00:08 STEP Adım üç | SKIPPED"""


def _web_scenario(**overrides: object) -> RawScenario:
    base = dict(
        scenario_name="Web senaryosu",
        platform=Platform.WEB,
        test_log=_TEST_LOG,
        dom_html="<html>form</html>",
        browser_log="console satırı",
        web_screenshot_path="attachments/web.png",
        mobile_screenshot_path="attachments/mobile.png",
    )
    base.update(overrides)
    return RawScenario(**base)  # type: ignore[arg-type]


def test_web_scenario_yields_full_findings(mock_extractor: MockExtractor) -> None:
    findings = mock_extractor.extract(_web_scenario(), bank="demo")

    assert findings.platform is Platform.WEB
    assert findings.bank == "demo"
    assert findings.failed_step == "Adım iki"
    assert "NoSuchElementException" in findings.error_message
    assert [step.status for step in findings.steps] == [
        StepStatus.PASSED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
    ]
    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_STEPS in labels  # ADIMLAR = raw test.log
    assert BLOCK_ERROR in labels  # HATA = identified error_message
    assert BLOCK_DOM in labels
    assert BLOCK_BROWSER in labels
    # Web platform stores only the web screenshot (mobile not expected).
    assert findings.screenshot_paths == ["attachments/web.png"]
    assert findings.missing_evidence == []


def test_mobile_scenario_has_no_web_blocks(mock_extractor: MockExtractor) -> None:
    scenario = RawScenario(
        scenario_name="Mobil senaryosu",
        platform=Platform.MOBILE,
        test_log=_TEST_LOG,
        mobile_screenshot_path="attachments/mobile.png",
    )

    findings = mock_extractor.extract(scenario)

    assert findings.platform is Platform.MOBILE
    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_DOM not in labels and BLOCK_BROWSER not in labels
    assert BLOCK_STEPS in labels and BLOCK_ERROR in labels
    assert findings.failed_step == "Adım iki"
    assert findings.screenshot_paths == ["attachments/mobile.png"]
    assert findings.missing_evidence == []


def test_hybrid_scenario_expects_web_files_and_mobile_shot(
    mock_extractor: MockExtractor,
) -> None:
    findings = mock_extractor.extract(_web_scenario(platform=Platform.HYBRID))

    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_DOM in labels and BLOCK_BROWSER in labels
    # hybrid stores the mobile screenshot (not the web one).
    assert findings.screenshot_paths == ["attachments/mobile.png"]


def test_missing_expected_evidence_is_tolerated_and_flagged(
    mock_extractor: MockExtractor,
) -> None:
    # Web scenario but the DOM never arrived (browser did not open).
    findings = mock_extractor.extract(_web_scenario(dom_html=""))

    assert isinstance(findings, Findings)
    assert "HtmlEvidence" in findings.missing_evidence
    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_DOM not in labels  # missing -> no DOM block, but no crash


def test_jenkins_console_log_becomes_console_block(
    mock_extractor: MockExtractor,
) -> None:
    from app.domain.findings import BLOCK_CONSOLE

    findings = mock_extractor.extract(
        _web_scenario(), jenkins_console_log="MOCK_jenkins line"
    )
    console_blocks = [
        b for b in findings.evidence_blocks if b.label == BLOCK_CONSOLE
    ]
    assert console_blocks and "MOCK_jenkins line" in console_blocks[0].content
