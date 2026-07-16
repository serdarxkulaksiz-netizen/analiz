"""Output JSON contract (plan.md A8) — flat, fixed schema.

`LLMAnalysis` = fields the LLM must return (field names English, text content
Turkish). `AnalysisResult` = the stored row: the same flat fields plus
system-side metadata the code attaches (the LLM never produces these).

No fabricated defaults for text fields (plan.md B3.9): if the LLM leaves a
field out, it stays empty.
"""

from pydantic import BaseModel

from app.domain.enums import Verdict


class AnalysisMeta(BaseModel):
    """System-side call metadata (plan.md A8 `meta`)."""

    llm_model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    analyzed_at: str = ""


class LLMAnalysis(BaseModel):
    """Exactly what the LLM is required to return (plan.md A8).

    `verdict` and `confidence` are mandatory: if missing or invalid the
    response is rejected and the scenario is marked `analysis_failed`
    (plan.md A9). `confidence` is stored as returned — no mapping.
    """

    scenario_name: str = ""
    platform: str = ""
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

    On `analysis_failed`, LLM analysis fields stay empty/None; only
    `scenario_name`/`platform` are filled by the system from Findings
    (factual identity, not fabricated analysis) so the row stays traceable.
    """

    # --- persistence keys (system) ---
    result_id: str
    analyzer_run_id: str

    # --- LLM fields (plan.md A8) ---
    scenario_name: str = ""
    platform: str = ""
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

    # --- system-side meta (plan.md A8; code attaches, LLM never produces) ---
    truncated: bool = False
    truncated_note: str = ""
    screenshot_path: str = ""
    raw_llm_response: str = ""
    analysis_failed: bool = False
    meta: AnalysisMeta = AnalysisMeta()
