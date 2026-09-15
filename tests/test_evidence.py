"""Evidence architecture tests: attachment mapping + profile flags."""

from functools import partial

from app.evidence.profiles import Profile, ProfileConfig
from app.evidence.registry import EvidenceRegistry
from app.evidence.types import WebScreenshotEvidence
from app.source.models import Attachment, RawScenario

_ALL = [
    "TestLogEvidence",
    "TestPropertiesEvidence",
    "HtmlEvidence",
    "MobileDomEvidence",
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


def _att(
    device: str, extension: str, mime: str = "text/plain", content: str = "x", path: str = ""
) -> Attachment:
    """One attachment, named the way VisiumGo names it: folder + device + number."""
    return Attachment(
        file_name=f"220807234/{device}_12345{extension}",
        mime_type=mime,
        device_id=device,
        content=content,
        stored_path=path,
    )


def _web_attachments() -> list[Attachment]:
    return [
        _att("test", ".log", content="steps"),
        _att("test", ".properties", content="retryNumber=1"),
        _att("browser.default", ".log", content="blog"),
        _att("browser.default", ".html", mime="text/html", content="<html/>"),
        _att("browser.default", ".png", mime="image/png", content="", path="web.png"),
    ]


def _scenario(attachments: list[Attachment]) -> RawScenario:
    return RawScenario(scenario_name="S", attachments=attachments)


def test_attachments_map_to_expected_classes() -> None:
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), _FULL_PROFILE)
    names = {type(e).evidence_name for e in evidences}
    assert names == {
        "TestLogEvidence",
        "TestPropertiesEvidence",
        "BrowserLogEvidence",
        "HtmlEvidence",
        "WebScreenshotEvidence",
    }


def test_two_text_plain_split_by_device_id() -> None:
    # text/plain + test -> TestLog ; text/plain + browser.default -> BrowserLog
    evidences = EvidenceRegistry().build_for(
        _scenario(
            [_att("test", ".log", content="T"), _att("browser.default", ".log", content="B")]
        ),
        _FULL_PROFILE,
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    # Each header names its own file, so two text/plain files from the same
    # device can never look like the same evidence.
    assert by_name["TestLogEvidence"].to_block().label.startswith("test.log · ")
    assert by_name["BrowserLogEvidence"].to_block().label.startswith("browser.default.log · ")


def test_test_log_and_test_properties_are_different_evidence() -> None:
    """Same mime, same device, different file: they must not share a class.

    They used to both match `text/plain` + `test`, so a profile asking for the
    step flow got the properties file inside the same prompt block.
    """
    evidences = EvidenceRegistry().build_for(
        _scenario(
            [
                _att("test", ".log", content="steps"),
                _att("test", ".properties", content="retryNumber=1"),
            ]
        ),
        _profile(["TestLogEvidence", "TestPropertiesEvidence"]),
    )
    blocks = {type(e).evidence_name: e.to_block() for e in evidences}
    assert blocks["TestLogEvidence"].label.startswith("test.log · ")
    assert blocks["TestLogEvidence"].content == "steps"
    assert blocks["TestPropertiesEvidence"].label.startswith("test.properties · ")


def test_test_properties_stays_out_of_the_prompt_by_default() -> None:
    """Faz 1 decision: stored, never prompted unless a profile asks for it."""
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("test", ".properties", content="retryNumber=1")]), _FULL_PROFILE
    )
    assert [type(e).evidence_name for e in evidences] == ["TestPropertiesEvidence"]
    assert evidences[0].to_block() is None


def test_mobile_dom_xml_is_its_own_evidence() -> None:
    """The mobile UI tree now arrives as its own `.xml` attachment (was in test.log)."""
    evidences = EvidenceRegistry().build_for(
        _scenario(
            [_att("mobile.android.Samsung-M31", ".xml", mime="text/xml", content="<hierarchy/>")]
        ),
        _profile(["MobileDomEvidence"]),
    )
    assert [type(e).evidence_name for e in evidences] == ["MobileDomEvidence"]
    # The device name travels in the header.
    assert evidences[0].to_block().label.startswith("mobile.android.Samsung-M31.xml · ")


def test_mobile_png_prefix_matches_mobile_screenshot() -> None:
    evidences = EvidenceRegistry().build_for(
        _scenario([_att("mobile.ios.iPhone 14 Pro Max", ".png", mime="image/png", path="m.png")]),
        _FULL_PROFILE,
    )
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["MobileScreenshotEvidence"].screenshot_path == "m.png"
    assert by_name["MobileScreenshotEvidence"].to_block() is None  # png not to LLM


def test_html_block_and_png_no_block() -> None:
    evidences = EvidenceRegistry().build_for(_scenario(_web_attachments()), _FULL_PROFILE)
    by_name = {type(e).evidence_name: e for e in evidences}
    assert by_name["HtmlEvidence"].to_block().label.startswith("browser.default.html · ")
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
        _scenario([_att("weird", ".pdf", mime="application/pdf", content="?")]), _FULL_PROFILE
    )
    assert evidences == []


def test_build_log_attachment_maps_to_build_evidence() -> None:
    profile = _profile(["BuildLogEvidence"])
    evidences = EvidenceRegistry().build_for(
        _scenario(
            [
                Attachment(
                    file_name="build.log",
                    mime_type="text/plain",
                    device_id="build",
                    content="job log",
                )
            ]
        ),
        profile,
    )
    assert [type(e).evidence_name for e in evidences] == ["BuildLogEvidence"]
    assert evidences[0].to_block().label.startswith("build.log · ")


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


def test_screenshot_path_is_only_ever_a_real_path() -> None:
    """A screenshot reference must open something, or not exist at all.

    `stored_path` empty has two causes — the profile skipped the file, and the
    download failed — and both used to fall back to the API's `fileName`, which
    is not a path on any disk. The field is read as "open this".
    """
    meta = {
        "file_name": "-125/browser.default_1.png",
        "mime_type": "image/png",
        "device_id": "browser.default",
    }
    failed = Attachment(**meta, stored_path="", download_skipped=False)
    skipped = Attachment(**meta, stored_path="", download_skipped=True)
    landed = Attachment(**meta, stored_path="/db/attachments/1/browser.default.png")

    build = partial(WebScreenshotEvidence.from_attachment, goes_to_llm=False, goes_to_store=True)
    assert build(failed).screenshot_path == ""
    assert build(skipped).screenshot_path == ""
    assert build(landed).screenshot_path == "/db/attachments/1/browser.default.png"
