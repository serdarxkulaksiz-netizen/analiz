"""Evidence architecture tests (plan.md A5): attachment mapping, flags, missing."""

from app.config import Settings
from app.domain.enums import Platform
from app.domain.findings import BLOCK_BROWSER, BLOCK_DOM, BLOCK_STEPS
from app.evidence.registry import EvidenceRegistry
from app.source.models import Attachment, RawScenario


def _att(mime: str, device: str, content: str = "x", path: str = "") -> Attachment:
    return Attachment(
        file_name=f"{device}.file",
        mime_type=mime,
        device_id=device,
        content=content,
        stored_path=path,
    )


def _web_attachments() -> list[Attachment]:
    return [
        _att("text/plain", "test", "steps"),
        _att("text/plain", "browser.default", "blog"),
        _att("text/html", "browser.default", "<html/>"),
        _att("image/png", "browser.default", "", "web.png"),
    ]


def _scenario(platform: Platform, attachments: list[Attachment]) -> RawScenario:
    return RawScenario(scenario_name="S", platform=platform, attachments=attachments)


def test_attachments_map_to_expected_classes(evidence_registry: EvidenceRegistry) -> None:
    evidences = evidence_registry.build_for(_scenario(Platform.WEB, _web_attachments()))
    names = {type(e).evidence_name for e in evidences}
    assert names == {
        "TestLogEvidence",
        "BrowserLogEvidence",
        "HtmlEvidence",
        "WebScreenshotEvidence",
    }


def test_two_text_plain_split_by_device_id(evidence_registry: EvidenceRegistry) -> None:
    # text/plain + test -> TestLog ; text/plain + browser.default -> BrowserLog
    evidences = evidence_registry.build_for(
        _scenario(
            Platform.WEB,
            [_att("text/plain", "test", "T"), _att("text/plain", "browser.default", "B")],
        )
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["TestLogEvidence"].to_block().label == BLOCK_STEPS
    assert by_name["BrowserLogEvidence"].to_block().label == BLOCK_BROWSER


def test_mobile_png_prefix_matches_mobile_screenshot(
    evidence_registry: EvidenceRegistry,
) -> None:
    evidences = evidence_registry.build_for(
        _scenario(
            Platform.MOBILE,
            [
                _att("text/plain", "test", "T"),
                _att("image/png", "mobile.ios.iPhone 14 Pro Max", "", "m.png"),
            ],
        )
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["MobileScreenshotEvidence"].screenshot_path == "m.png"
    assert by_name["MobileScreenshotEvidence"].to_block() is None  # png not to LLM


def test_html_block_and_png_no_block(evidence_registry: EvidenceRegistry) -> None:
    evidences = evidence_registry.build_for(_scenario(Platform.WEB, _web_attachments()))
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["HtmlEvidence"].to_block().label == BLOCK_DOM
    assert by_name["WebScreenshotEvidence"].to_block() is None


def test_flag_override_stops_evidence_going_to_llm(settings: Settings) -> None:
    flags = {**settings.evidence_flags}
    flags["BrowserLogEvidence"] = {"goes_to_llm": False, "goes_to_store": True}
    registry = EvidenceRegistry(flags)
    evidences = registry.build_for(_scenario(Platform.WEB, _web_attachments()))
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["BrowserLogEvidence"].to_block() is None  # config-only change


def test_missing_expected_evidence_is_flagged(
    evidence_registry: EvidenceRegistry,
) -> None:
    # Web scenario but no HTML attachment arrived (browser did not open).
    attachments = [a for a in _web_attachments() if a.mime_type != "text/html"]
    scenario = _scenario(Platform.WEB, attachments)
    evidences = evidence_registry.build_for(scenario)
    missing = evidence_registry.missing_names(Platform.WEB, evidences)
    assert "HtmlEvidence" in missing


def test_unknown_attachment_is_skipped(evidence_registry: EvidenceRegistry) -> None:
    evidences = evidence_registry.build_for(
        _scenario(Platform.WEB, [_att("application/pdf", "weird", "?")])
    )
    assert evidences == []
