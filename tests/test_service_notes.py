"""What the stored rows SAY when there is no prompt and no diagnosis.

These strings are the only thing a person has when a scenario produced nothing,
so each one has to be read from what actually happened — never guessed from
what is missing.
"""

from app.domain.findings import AttachmentReport, EvidenceReport, Findings, JobLogReport
from app.service import _skipped_reason, _total_scenarios_note


def _findings(**overrides: object) -> Findings:
    base: dict[str, object] = {"scenario_name": "Senaryo", "profile_name": "default_web"}
    base.update(overrides)
    return Findings(**base)  # type: ignore[arg-type]


def test_a_built_prompt_needs_no_reason() -> None:
    assert _skipped_reason("PROMPT", _findings(), False, "llm") == ""


def test_precheck_is_read_from_who_answered_not_guessed() -> None:
    """The trap this closes: blaming PreCheck for someone else's crash.

    "no prompt and no evidence gap" was ALSO true when building the prompt
    raised, so a template error was recorded as "a PreCheck rule answered" —
    a rule that had never run.
    """
    assert "precheck" in _skipped_reason("", _findings(), False, "precheck")

    crashed = _skipped_reason("", _findings(), False, "")
    assert "precheck" not in crashed
    assert "prompt kurulamadı" in crashed


def test_extraction_failure_says_so() -> None:
    assert "kanıt çıkarımı" in _skipped_reason("", None, False, "")


def test_unreadable_scenario_detail_outranks_the_missing_file_list() -> None:
    """Its attachments are empty for a reason that is not about the run."""
    report = EvidenceReport(scenario_error="/results satırında 'id' alanı yok")
    reason = _skipped_reason("", _findings(evidence_report=report), True, "")
    assert "senaryo detayı okunamadı" in reason


def test_missing_evidence_names_the_files_and_why() -> None:
    report = EvidenceReport(
        attachments=[
            AttachmentReport(
                file_name="-125/browser.default_1.html",
                evidence_name="HtmlEvidence",
                goes_to_llm=True,
                download_error="500 Server Error",
            )
        ],
        job_log=JobLogReport(goes_to_llm=True, error="404"),
    )
    reason = _skipped_reason("", _findings(evidence_report=report), True, "")

    assert "default_web" in reason  # which profile was in charge
    assert "browser.default_1.html" in reason  # which file
    assert "500 Server Error" in reason  # and why it is not here
    assert "build.log (404)" in reason  # the job log says its own reason


def test_absent_scenario_total_is_reported_not_substituted() -> None:
    assert _total_scenarios_note({"totalScenarios": 100}) == ""
    assert "bilinmiyor" in _total_scenarios_note({"state": "PASSED"})
