"""Contract tests: frozen field names and enum values (plan.md A6, A10, B3.2)."""

from app.domain.enums import AnalysisStatus, RunStatus, StepStatus, Verdict
from app.domain.findings import Findings
from app.domain.result import AnalysisResult, LLMAnalysis


def test_findings_contract_fields_are_frozen() -> None:
    assert set(Findings.model_fields) == {
        "parameter1",
        "parameter2",
        "scenario_name",
        "failed_step",
        "error_message",
        "steps",
        "evidence_blocks",
        "screenshot_paths",
        "retry_info",
        "profile_name",
        "extra_context",
        "truncated",
        "truncated_note",
        "excluded_from_store",
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
        "parameter1",
        "parameter2",
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
    assert {status.value for status in StepStatus} == {"PASSED", "FAILED", "SKIPPED"}
    assert {status.value for status in AnalysisStatus} == {"ok", "analysis_failed"}
