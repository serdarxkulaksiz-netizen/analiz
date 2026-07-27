"""EvidenceExtractor tests: RawScenario -> Findings (plan.md A5, A6)."""

from app.domain.enums import Platform, StepStatus
from app.domain.findings import (
    BLOCK_BROWSER,
    BLOCK_CONSOLE,
    BLOCK_DOM,
    BLOCK_ERROR,
    BLOCK_STEPS,
    Step,
)
from app.extraction.evidence_extractor import EvidenceExtractor
from app.source.models import Attachment, RawScenario


def _att(mime: str, device: str, content: str = "x", path: str = "") -> Attachment:
    return Attachment(
        file_name=f"{device}.file",
        mime_type=mime,
        device_id=device,
        content=content,
        stored_path=path,
    )


def _web_scenario(**overrides: object) -> RawScenario:
    base = dict(
        scenario_name="Web senaryosu",
        platform=Platform.WEB,
        error_text="NoSuchElementException: #btn",
        steps=[
            Step(name="Adım bir", status=StepStatus.PASSED),
            Step(name="Adım iki", status=StepStatus.FAILED),
        ],
        attachments=[
            _att("text/plain", "test", "test log"),
            _att("text/plain", "browser.default", "browser log"),
            _att("text/html", "browser.default", "<html/>"),
            _att("image/png", "browser.default", "", "web.png"),
        ],
    )
    base.update(overrides)
    return RawScenario(**base)  # type: ignore[arg-type]


def test_web_scenario_full_findings(extractor: EvidenceExtractor) -> None:
    findings = extractor.extract(_web_scenario(), bank="demo")

    assert findings.platform is Platform.WEB
    assert findings.bank == "demo"
    assert findings.failed_step == "Adım iki"  # first FAILED step
    assert findings.error_message == "NoSuchElementException: #btn"
    labels = [b.label for b in findings.evidence_blocks]
    assert BLOCK_STEPS in labels  # test.log
    assert BLOCK_BROWSER in labels
    assert BLOCK_DOM in labels
    assert BLOCK_ERROR in labels  # HATA = error_text
    assert findings.screenshot_paths == ["web.png"]
    assert findings.missing_evidence == []


def test_mobile_scenario_expects_mobile_shot(extractor: EvidenceExtractor) -> None:
    scenario = RawScenario(
        scenario_name="Mobil",
        platform=Platform.MOBILE,
        error_text="boom",
        steps=[Step(name="x", status=StepStatus.FAILED)],
        attachments=[
            _att("text/plain", "test", "log"),
            _att("image/png", "mobile.android.samsung", "", "m.png"),
        ],
    )
    findings = extractor.extract(scenario)
    labels = [b.label for b in findings.evidence_blocks]
    assert BLOCK_DOM not in labels and BLOCK_BROWSER not in labels
    assert findings.screenshot_paths == ["m.png"]
    assert findings.missing_evidence == []


def test_missing_html_is_flagged(extractor: EvidenceExtractor) -> None:
    scenario = _web_scenario(
        attachments=[_att("text/plain", "test", "log")]  # only test.log
    )
    findings = extractor.extract(scenario)
    assert "HtmlEvidence" in findings.missing_evidence
    assert "BrowserLogEvidence" in findings.missing_evidence


def test_jenkins_console_log_block(extractor: EvidenceExtractor) -> None:
    findings = extractor.extract(_web_scenario(), jenkins_console_log="jenkins out")
    console = [b for b in findings.evidence_blocks if b.label == BLOCK_CONSOLE]
    assert console and "jenkins out" in console[0].content
