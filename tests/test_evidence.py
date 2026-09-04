"""Evidence architecture tests (plan.md A5): attachment mapping + profile flags."""

from app.domain.findings import BLOCK_BROWSER, BLOCK_DOM, BLOCK_STEPS
from app.evidence.profiles import Profile, ProfileConfig
from app.evidence.registry import EvidenceRegistry
from app.source.models import Attachment, RawScenario

_ALL = [
    "TestLogEvidence",
    "HtmlEvidence",
    "BrowserLogEvidence",
    "BuildLogEvidence",
    "WebScreenshotEvidence",
    "MobileScreenshotEvidence",
]


def _profile(to_llm: list[str], rules: dict | None = None) -> Profile:
    return Profile(
        "test",
        ProfileConfig(evidence_to_llm=to_llm, evidence_to_store=_ALL, rules=rules or {}),
    )


_FULL_PROFILE = _profile(["TestLogEvidence", "HtmlEvidence", "BrowserLogEvidence"])


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


def _scenario(attachments: list[Attachment]) -> RawScenario:
    return RawScenario(scenario_name="S", attachments=attachments)


def test_attachments_map_to_expected_classes() -> None:
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), _FULL_PROFILE)
    names = {type(e).evidence_name for e in evidences}
    assert names == {
        "TestLogEvidence",
        "BrowserLogEvidence",
        "HtmlEvidence",
        "WebScreenshotEvidence",
    }


def test_two_text_plain_split_by_device_id() -> None:
    # text/plain + test -> TestLog ; text/plain + browser.default -> BrowserLog
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("text/plain", "test", "T"), _att("text/plain", "browser.default", "B")]),
        _FULL_PROFILE,
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["TestLogEvidence"].to_block().label == BLOCK_STEPS
    assert by_name["BrowserLogEvidence"].to_block().label == BLOCK_BROWSER


def test_mobile_png_prefix_matches_mobile_screenshot() -> None:
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("image/png", "mobile.ios.iPhone 14 Pro Max", "", "m.png")]),
        _FULL_PROFILE,
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["MobileScreenshotEvidence"].screenshot_path == "m.png"
    assert by_name["MobileScreenshotEvidence"].to_block() is None  # png not to LLM


def test_html_block_and_png_no_block() -> None:
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), _FULL_PROFILE)
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["HtmlEvidence"].to_block().label == BLOCK_DOM
    assert by_name["WebScreenshotEvidence"].to_block() is None


def test_profile_controls_llm_flag() -> None:
    # Profile without BrowserLog in evidence_to_llm: its block disappears —
    # a config-only change, no code.
    minimal = _profile(["TestLogEvidence"])
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), minimal)
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["TestLogEvidence"].to_block() is not None
    assert by_name["BrowserLogEvidence"].to_block() is None
    assert by_name["HtmlEvidence"].to_block() is None


def test_unknown_attachment_is_skipped() -> None:
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("application/pdf", "weird", "?")]), _FULL_PROFILE
    )
    assert evidences == []


def test_build_log_attachment_maps_to_build_evidence() -> None:
    profile = _profile(["BuildLogEvidence"])
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("text/plain", "build", "job log")]), profile
    )
    assert [type(e).evidence_name for e in evidences] == ["BuildLogEvidence"]
    assert evidences[0].to_block().label == "BUILD LOG"


def test_profile_rules_are_applied_to_content() -> None:
    # A rule on HtmlEvidence must shape only that evidence's content.
    profile = _profile(
        ["TestLogEvidence", "HtmlEvidence"],
        rules={"HtmlEvidence": [{"type": "max_chars", "n": 4}]},
    )
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), profile)
    by_name = {type(e).evidence_name: e for e in evidences}

    assert by_name["HtmlEvidence"].was_trimmed is True
    assert by_name["HtmlEvidence"].to_block().content.startswith("<htm")
    # test.log has no rules -> untouched
    assert by_name["TestLogEvidence"].was_trimmed is False
    assert by_name["TestLogEvidence"].to_block().content == "steps"
