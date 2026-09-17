"""API response contract — what `GET /analyze/visiumgo/{id}` actually shows."""

from typing import Any

from pydantic import BaseModel

from app.domain.enums import AnalysisStatus, RunStatus, Verdict
from app.domain.result import AnalysisMeta


class DiagnosisView(BaseModel):
    """One scenario's diagnosis, as the API exposes it."""

    result_id: str = ""

    scenario_name: str = ""
    root_cause: str = ""
    error_type: str = ""
    verdict: Verdict | None = None
    explanation: str = ""
    suggestion: str = ""
    confidence: float | None = None
    confidence_reason: str = ""
    summary: str = ""
    most_relevant_log_lines: list[str] = []
    error_signature: str = ""

    status: AnalysisStatus = AnalysisStatus.OK
    failure_reason: str = ""
    meta: AnalysisMeta = AnalysisMeta()


class RunView(BaseModel):
    """An analyzer run's status plus its finished diagnoses."""

    analyzer_run_id: str = ""
    status: RunStatus | None = None
    job_id: str = ""
    run_id: str = ""
    job_name: str = ""
    parameter1: str = ""
    parameter2: str = ""
    scenario_count: int = 0
    completed_count: int = 0
    total_scenario_count: int = 0
    note: str = ""
    build_log_error: str = ""
    created_at: str = ""
    updated_at: str = ""
    results: list[DiagnosisView] = []


def build_run_view(run: dict[str, Any]) -> RunView:
    """Project a stored run row (with its results) into the API view."""
    return RunView(
        **{key: value for key, value in run.items() if key != "results"},
        results=[DiagnosisView(**row) for row in run.get("results", [])],
    )
