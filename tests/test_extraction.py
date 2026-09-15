"""EvidenceExtractor tests: RawScenario -> Findings."""

from collections.abc import Callable

from app.domain.findings import Findings
from app.source.models import Attachment, JobLog, RawScenario


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


def test_default_profile_full_findings(extract: Callable[..., Findings]) -> None:
    findings = extract(_scenario())

    # Order follows the profile's evidence_to_llm list, and the header names
    # the file the way VisiumGo does.
    assert [b.evidence_name for b in findings.evidence_blocks] == [
        "TestLogEvidence",
        "HtmlEvidence",
    ]
    labels = [b.label for b in findings.evidence_blocks]
    assert labels[0].startswith("test.log · ")
    assert labels[1].startswith("browser.default.html · ")
    # The screenshot is recognised, so it is not reported as an unclaimed file —
    # and it produces no prompt block.
    png = next(r for r in findings.evidence_report.attachments if r.file_name.endswith(".png"))
    assert png.evidence_name == "WebScreenshotEvidence"
    assert png.stored_path == "web.png"


def test_request_parameters_never_reach_extraction(extract: Callable[..., Findings]) -> None:
    """`Findings` has no parameter fields at all — they decide nothing.

    Keeping them in the analysis contract invited exactly what happened before:
    they crept into profile selection and into the prompt.
    """
    findings = extract(_scenario())

    assert not hasattr(findings, "parameter1")
    assert not hasattr(findings, "parameter2")
    assert findings.profile_name == "default_web"  # job mapping alone decided
    names = [b.evidence_name for b in findings.evidence_blocks]
    assert "TestLogEvidence" in names and "HtmlEvidence" in names


def test_missing_evidence_produces_no_block_at_all(
    extract: Callable[..., Findings],
) -> None:
    """Profile wants DOM but it never arrived -> no block, no header, no marker."""
    scenario = _scenario(
        attachments=[_att("test", ".log", content="test log")]  # no html at all
    )
    findings = extract(scenario)

    assert not [b for b in findings.evidence_blocks if b.evidence_name == "HtmlEvidence"]
    # Present evidence is untouched.
    test_log = next(b for b in findings.evidence_blocks if b.evidence_name == "TestLogEvidence")
    assert test_log.content == "test log"


def test_empty_evidence_also_produces_no_block(extract: Callable[..., Findings]) -> None:
    # Attachment arrived but the download failed -> empty content, same result.
    scenario = _scenario(
        attachments=[
            _att("test", ".log", content="test log"),
            _att("browser.default", ".html", mime="text/html", content=""),
        ]
    )
    findings = extract(scenario)
    assert not [b for b in findings.evidence_blocks if b.evidence_name == "HtmlEvidence"]


def test_build_log_is_profile_controlled(extract: Callable[..., Findings]) -> None:
    # The default profile does NOT send the job-level build log (it holds all
    # scenarios and would bloat every prompt); a profile must opt in.
    findings = extract(_scenario(), job_log=JobLog(text="build out"))
    assert not [b for b in findings.evidence_blocks if b.evidence_name == "BuildLogEvidence"]


def test_evidence_report_shows_what_arrived_and_what_matched(
    extract: Callable[..., Findings],
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

    report = extract(scenario).evidence_report

    unmatched = [row.file_name for row in report.attachments if not row.evidence_name]
    assert "beklenmeyen.pdf" in unmatched
    by_name = {row.file_name: row for row in report.attachments}
    assert by_name["beklenmeyen.pdf"].evidence_name == ""  # nothing claimed it
    test_log = "220807234/test_12345.log"
    assert by_name[test_log].evidence_name == "TestLogEvidence"
    assert by_name[test_log].goes_to_llm is True
    assert by_name[test_log].chars > 0

    blocks = {row.label.split(" · ")[0]: row for row in report.blocks}
    assert blocks["test.log"].available is True
    assert blocks["test.log"].chars > 0


def test_report_never_invents_a_file_path(extract: Callable[..., Findings]) -> None:
    """`stored_path` is where the file landed, or nothing at all.

    Two different pieces of code used to fall back to the API's `fileName` when
    a download had not landed. `fileName` is not a path on any disk, and this
    field is read as "open this".
    """
    landed = _att("browser.default", ".png", mime="image/png", path="/db/web.png")
    failed = _att("mobile.android.s", ".png", mime="image/png", path="")

    report = extract(_scenario(attachments=[landed, failed])).evidence_report
    by_class = {row.evidence_name: row for row in report.attachments}

    assert by_class["WebScreenshotEvidence"].stored_path == "/db/web.png"
    assert by_class["MobileScreenshotEvidence"].stored_path == ""
