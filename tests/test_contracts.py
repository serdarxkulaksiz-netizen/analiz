"""Contract tests: frozen field names and enum values."""

from pathlib import Path

from app.domain.enums import AnalysisStatus, RunStatus, Verdict
from app.domain.findings import Findings
from app.domain.result import AnalysisResult, LLMAnalysis
from app.prompting.builder import KNOWN_PLACEHOLDERS


def test_findings_contract_fields_are_frozen() -> None:
    # No `parameter1`/`parameter2`: request keys that decide nothing have no
    # place in the analysis contract. No `error_message`/`steps` either: the
    # prompt carries evidence blocks and nothing else.
    assert set(Findings.model_fields) == {
        "scenario_name",
        "evidence_blocks",
        "screenshot_paths",
        "retry_info",
        "profile_name",
        "prompt_template",
        "extra_context",
        "truncated",
        "truncated_note",
        "excluded_from_store",
        "evidence_report",
    }


def test_llm_analysis_contract_fields_are_frozen() -> None:
    assert set(LLMAnalysis.model_fields) == {
        "scenario_name",
        "root_cause",
        "error_type",
        "verdict",
        "explanation",
        "suggestion",
        "confidence",
        "confidence_reason",
        "summary",
        "most_relevant_log_lines",
        "error_signature",
    }


def test_analysis_result_adds_only_system_meta() -> None:
    system_fields = set(AnalysisResult.model_fields) - set(LLMAnalysis.model_fields)
    assert system_fields == {
        "result_id",
        "analyzer_run_id",
        "failure_reason",
        "profile_name",
        "truncated",
        "truncated_note",
        "screenshot_paths",
        "raw_llm_response",
        "status",
        "meta",
    }


def test_verdict_values_are_frozen() -> None:
    assert {verdict.value for verdict in Verdict} == {
        "test_maintenance",
        "application_bug",
        "environment_error",
        "transient_error",
        "unknown",
        "inconclusive",
    }


def test_status_values_are_frozen() -> None:
    assert {status.value for status in RunStatus} == {
        "pending",
        "running",
        "done",
        "failed",
    }
    assert {status.value for status in AnalysisStatus} == {
        "ok",
        "analysis_failed",
        # The LLM was never called because no evidence reached the prompt —
        # deliberately distinct from a failed analysis.
        "no_evidence",
    }


def test_request_parameters_reach_no_decision() -> None:
    """`parameter1`/`parameter2` must stay out of every decision.

    They are reserved request keys: recorded on the run, returned by GET, and
    that is all. This is a guard, not a style check — they have crept back into
    profile selection, the prompt and the (since removed) cache key once each,
    and every time the symptom was a silently different analysis.
    """
    import inspect

    from app.evidence.planner import AttachmentPlanner
    from app.evidence.profiles import ProfileRegistry
    from app.extraction.base import Extractor
    from app.prompting.builder import KNOWN_PLACEHOLDERS
    from app.service import AnalyzerService

    reserved = {"parameter1", "parameter2"}

    for func in (
        ProfileRegistry.get,
        AttachmentPlanner.wants_for,
        Extractor.extract,
        AnalyzerService._analyze_scenario,
    ):
        assert not reserved & set(inspect.signature(func).parameters), func.__qualname__

    assert not reserved & KNOWN_PLACEHOLDERS  # no prompt placeholder either
    assert not reserved & set(Findings.model_fields)
    assert not reserved & set(AnalysisResult.model_fields)

    # The one place they legitimately appear: the run row the API shows.
    assert reserved <= set(inspect.signature(AnalyzerService.create_run).parameters)


def test_scenario_error_and_steps_never_reach_the_analysis() -> None:
    """`errorText` stops at the scenario; `stepResults` is not read at all.

    VisiumGo derives both by parsing `test.log`, which the profile sends whole,
    so carrying them further shipped the same text twice. `error_text` is kept
    on `RawScenario` for one future reader — PreCheck, which will look at it
    before any attachment is downloaded.
    """
    from app.source.models import RawScenario

    assert "error_text" in RawScenario.model_fields
    assert "steps" not in RawScenario.model_fields

    for field in ("error_message", "failed_step", "steps"):
        assert field not in Findings.model_fields
    for placeholder in ("error_message", "failed_step", "steps"):
        assert placeholder not in KNOWN_PLACEHOLDERS

    templates = sorted(Path("config/prompts").glob("*.txt"))
    assert templates
    for path in templates:
        text = path.read_text(encoding="utf-8")
        for placeholder in ("$error_message", "$failed_step", "$steps"):
            assert placeholder not in text, f"{path.name} hâlâ {placeholder} kullanıyor"
