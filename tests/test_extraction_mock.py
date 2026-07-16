"""MockExtractor tests: Findings contract is honored for web and mobile."""

from app.domain.enums import Platform, StepStatus
from app.domain.findings import BLOCK_CONSOLE, BLOCK_DOM
from app.extraction.mock import MockExtractor
from app.source.models import RawScenario

_TEST_LOG = """2026-07-16 10:00:01 STEP Adım bir | PASSED
2026-07-16 10:00:07 STEP Adım iki | FAILED
2026-07-16 10:00:07 ERROR NoSuchElementException: #btn
2026-07-16 10:00:08 STEP Adım üç | SKIPPED"""


def test_web_scenario_yields_full_findings() -> None:
    scenario = RawScenario(
        scenario_name="Web senaryosu",
        platform=Platform.WEB,
        test_log=_TEST_LOG,
        browser_log="console satırı",
        dom_html="<html>form</html>",
        screenshot_path="attachments/shot.png",
    )

    findings = MockExtractor().extract(scenario)

    assert findings.platform is Platform.WEB
    assert findings.failed_step == "Adım iki"
    assert "NoSuchElementException" in findings.error_message
    assert [step.status for step in findings.steps] == [
        StepStatus.PASSED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
    ]
    assert findings.ui_excerpt == "<html>form</html>"
    assert findings.screenshot_path == "attachments/shot.png"
    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_DOM in labels and BLOCK_CONSOLE in labels


def test_mobile_scenario_has_no_ui_blocks() -> None:
    scenario = RawScenario(
        scenario_name="Mobil senaryosu",
        platform=Platform.MOBILE,
        test_log=_TEST_LOG,
        screenshot_path="attachments/mobile.png",
    )

    findings = MockExtractor().extract(scenario)

    assert findings.platform is Platform.MOBILE
    assert findings.ui_excerpt == ""  # empty on mobile, no fabricated content
    labels = [block.label for block in findings.evidence_blocks]
    assert BLOCK_DOM not in labels and BLOCK_CONSOLE not in labels
    assert findings.failed_step == "Adım iki"
