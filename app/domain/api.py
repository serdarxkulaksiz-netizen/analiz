"""API response contract — what `GET /analyze/visiumgo/{id}` actually shows.

Deliberately narrower than what is stored: `database/` keeps the FULL trace
(raw VisiumGo responses, the build log, the prompt sent, the complete LLM
envelope), but the API returns only the diagnosis the LLM produced plus the
small amount of system state a caller needs to make sense of it.

The projection lives here — at the API boundary — and NOT in
`AnalyzerService.get_run()`, which keeps returning the full row for internal
use and debugging.
"""

from typing import Any

from pydantic import BaseModel

from app.domain.enums import AnalysisStatus, RunStatus, Verdict
from app.domain.result import AnalysisMeta


class DiagnosisView(BaseModel):
    """One scenario's diagnosis, as the API exposes it."""

    #: Join key to the `evidence` / `prompts` / `llm_responses` rows on disk,
    #: so the full trace behind this diagnosis can still be found.
    result_id: str = ""

    # --- what the LLM answered (plan.md A10) ---
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

    # --- minimal system state: did it work, and who answered ---
    status: AnalysisStatus = AnalysisStatus.OK
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
    #: Set when this run reused an earlier run's results (cache hit).
    cached_from: str = ""
    created_at: str = ""
    updated_at: str = ""
    results: list[DiagnosisView] = []


def build_run_view(run: dict[str, Any]) -> RunView:
    """Project a stored run row (with its results) into the API view.

    Unknown/extra keys in the stored row are dropped by the model, which is
    the point: new persisted fields never leak into the API by accident.
    """
    return RunView(
        **{key: value for key, value in run.items() if key != "results"},
        results=[DiagnosisView(**row) for row in run.get("results", [])],
    )
