"""EvidenceExtractor tests: RawScenario -> Findings."""

import pytest

from app.extraction.evidence_extractor import EvidenceExtractor
from app.source.models import Attachment, RawScenario


def _att(
    device: str, extension: str, mime: str = "text/plain", content: str = "x", path: str = ""
) -> Attachment:
    """One attachment, named like VisiumGo names it (folder + device + number)."""
    return Attachment(
        file_name=f"220807234/{device}_12345{extension}",
        mime_type=mime,
        device_id=device,
        content=content,
        stored_path=path,
    )


def _scenario(**overrides: object) -> RawScenario:
    base: dict[str, object] = {
        "scenario_name": "Senaryo",
        # Kept on the scenario for PreCheck's future use; it must not reach the
        # prompt, because VisiumGo derives it from test.log.
        "error_text": "NoSuchElementException: #btn",
        "attachments": [
            _att("test", ".log", content="test log"),
            _att("browser.default", ".log", content="browser log"),
            _att("browser.default", ".html", mime="text/html", content="<html/>"),
            _att("browser.default", ".png", mime="image/png", content="", path="web.png"),
        ],
        "raw_detail": {"properties": {"x": "1"}},
    }
    base.update(overrides)
    return RawScenario(**base)  # type: ignore[arg-type]


def test_default_profile_full_findings(extractor: EvidenceExtractor) -> None:
    findings = extractor.extract(_scenario())

    # Order follows the profile's evidence_to_llm list, and the header names
    # the file the way VisiumGo does.
    assert [b.evidence_name for b in findings.evidence_blocks] == [
        "TestLogEvidence",
        "HtmlEvidence",
    ]
    labels = [b.label for b in findings.evidence_blocks]
    assert labels[0].startswith("test.log · ")
    assert labels[1].startswith("browser.default.html · ")
    assert findings.screenshot_paths == ["web.png"]


def test_request_parameters_never_reach_extraction(extractor: EvidenceExtractor) -> None:
    """`Findings` has no parameter fields at all — they decide nothing.

    Keeping them in the analysis contract invited exactly what happened before:
    they crept into profile selection and into the prompt.
    """
    findings = extractor.extract(_scenario())

    assert not hasattr(findings, "parameter1")
    assert not hasattr(findings, "parameter2")
    assert findings.profile_name == "default_web"  # job mapping alone decided
    names = [b.evidence_name for b in findings.evidence_blocks]
    assert "TestLogEvidence" in names and "HtmlEvidence" in names


def test_unknown_forced_profile_raises(extractor: EvidenceExtractor) -> None:
    # Loud failure instead of silently analyzing with the wrong profile.
    with pytest.raises(ValueError, match="Unknown profile"):
        extractor.extract(_scenario(), forced_profile="boyle-profil-yok")


def test_missing_evidence_produces_no_block_at_all(
    extractor: EvidenceExtractor,
) -> None:
    """Profile wants DOM but it never arrived -> no block, no header, no marker."""
    scenario = _scenario(
        attachments=[_att("test", ".log", content="test log")]  # no html at all
    )
    findings = extractor.extract(scenario)

    assert not [b for b in findings.evidence_blocks if b.evidence_name == "HtmlEvidence"]
    # Present evidence is untouched.
    test_log = next(b for b in findings.evidence_blocks if b.evidence_name == "TestLogEvidence")
    assert test_log.content == "test log"


def test_empty_evidence_also_produces_no_block(extractor: EvidenceExtractor) -> None:
    # Attachment arrived but the download failed -> empty content, same result.
    scenario = _scenario(
        attachments=[
            _att("test", ".log", content="test log"),
            _att("browser.default", ".html", mime="text/html", content=""),
        ]
    )
    findings = extractor.extract(scenario)
    assert not [b for b in findings.evidence_blocks if b.evidence_name == "HtmlEvidence"]


def test_build_log_is_profile_controlled(extractor: EvidenceExtractor) -> None:
    # The default profile does NOT send the job-level build log (it holds all
    # scenarios and would bloat every prompt); a profile must opt in.
    findings = extractor.extract(_scenario(), build_log="build out")
    assert not [b for b in findings.evidence_blocks if b.evidence_name == "BuildLogEvidence"]


def test_evidence_report_shows_what_arrived_and_what_matched(
    extractor: EvidenceExtractor,
) -> None:
    """One real run must answer "did it not arrive, or did it not match?".

    An attachment whose device_id/extension no Evidence claims used to vanish
    without trace: the block simply vanished from the prompt and the cause was
    indistinguishable from the file never being produced.
    """
    scenario = _scenario()
    scenario.attachments.append(
        Attachment(
            file_name="beklenmeyen.pdf",
            mime_type="application/pdf",
            device_id="unknown-device",
            content="?",
        )
    )

    report = extractor.extract(scenario).evidence_report

    assert "beklenmeyen.pdf" in report.unmatched
    by_name = {row.file_name: row for row in report.attachments}
    assert by_name["beklenmeyen.pdf"].evidence_name == ""  # nothing claimed it
    test_log = "220807234/test_12345.log"
    assert by_name[test_log].evidence_name == "TestLogEvidence"
    assert by_name[test_log].goes_to_llm is True
    assert by_name[test_log].chars > 0

    blocks = {row.label.split(" · ")[0]: row for row in report.blocks}
    assert blocks["test.log"].available is True
    assert blocks["test.log"].chars > 0
