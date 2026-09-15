"""What the stored rows SAY when there is no prompt and no diagnosis.

These strings are the only thing a person has when a scenario produced nothing,
so each one has to be read from what actually happened — never guessed from
what is missing.
"""

from app.domain.findings import AttachmentReport, EvidenceReport, Findings, JobLogReport
from app.service import (
    _forced_note,
    _running_note,
    _skipped_reason,
    _total_scenarios_note,
)


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


def test_an_unfinished_run_says_so_on_the_row() -> None:
    """A diagnosis from a half-written run must not read like a complete one.

    Only a caller naming a `run_id` can get here, and only deliberately — but
    what they get back is whatever evidence existed at that moment: fewer
    scenarios, half-written logs, screenshots not taken yet.
    """
    note = _running_note("RUNNING")
    assert "RUNNING" in note and "eksik olabilir" in note

    assert _running_note("PASSED") == ""
    assert _running_note("FAILED") == ""
    assert _running_note("") == ""


def test_a_run_with_no_failures_still_says_what_it_has_to_say() -> None:
    """The early exit used to write its own note and drop every other one.

    The case that matters: a RUNNING run with no failed scenarios YET reported
    "analiz edilecek hata yok" and no warning at all. That reading is backwards
    — the run had not finished, so "no errors" was not a result, it was a
    snapshot of an unfinished run.
    """
    notes = [
        n for n in (_running_note("RUNNING"), _forced_note(""), _total_scenarios_note({})) if n
    ]
    line = " · ".join([*notes, "analiz edilecek hata yok"])

    assert "RUNNING" in line  # the warning survives
    assert "totalScenarios gelmedi" in line  # and so does the other one
    assert line.endswith("analiz edilecek hata yok")
