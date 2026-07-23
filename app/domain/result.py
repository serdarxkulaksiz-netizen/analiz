"""Output JSON contract (plan.md A10) — flat, fixed schema.

`LLMAnalysis` = fields the LLM must return (field names English, text content
Turkish). `AnalysisResult` = the stored row: the same flat fields plus
system-side metadata the code attaches (the LLM never produces these — notably
`platform`/`bank`, which come from the request/Findings, not the model).

No fabricated defaults for text fields (plan.md A10): if the LLM leaves a
field out, it stays empty.
"""

from pydantic import BaseModel

from app.domain.enums import AnalysisStatus, Verdict


class AnalysisMeta(BaseModel):
    """System-side call metadata (plan.md A10 `meta`)."""

    llm_model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    analyzed_at: str = ""


class LLMAnalysis(BaseModel):
    """Exactly what the LLM is required to return (plan.md A10).

    `verdict` and `confidence` are mandatory: if missing or invalid the
    response is rejected and the scenario is marked `analysis_failed`
    (plan.md A9). `confidence` is stored as returned — no mapping. `platform`
    is NOT here — the system attaches it (A10 system-side meta).
    """

    scenario_name: str = ""
    root_cause: str = ""
    error_type: str = ""
    verdict: Verdict
    explanation: str = ""
    suggestion: str = ""
    confidence: float
    confidence_reason: str = ""
    summary: str = ""
    most_relevant_log_lines: list[str] = []
    error_signature: str = ""


class AnalysisResult(BaseModel):
    """Stored analysis row: LLM fields (flat) + system-side meta.

    On `status=analysis_failed`, LLM analysis fields stay empty/None; only
    `scenario_name`/`platform`/`bank` are filled by the system from the
    request/Findings (factual identity, not fabricated analysis) so the row
    stays traceable.
    """

    # --- persistence keys (system) ---
    result_id: str
    analyzer_run_id: str

    # --- LLM fields (plan.md A10) ---
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

    # --- system-side meta (plan.md A10; code attaches, LLM never produces) ---
    platform: str = ""
    bank: str = ""
    truncated: bool = False
    truncated_note: str = ""
    screenshot_paths: list[str] = []
    missing_evidence: list[str] = []
    raw_llm_response: str = ""
    status: AnalysisStatus = AnalysisStatus.OK
    meta: AnalysisMeta = AnalysisMeta()
