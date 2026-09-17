"""Output JSON contract — flat, fixed schema."""

from pydantic import BaseModel

from app.domain.enums import AnalysisStatus, Verdict


class AnalysisMeta(BaseModel):
    """System-side call metadata (`meta`)."""

    answered_by: str = ""
    llm_model: str = ""
    prompt_template: str = ""
    prompt_version: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    analyzed_at: str = ""


class LLMAnalysis(BaseModel):
    """Exactly what the LLM is required to return."""

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
    """Stored analysis row: LLM fields (flat) + system-side meta."""

    result_id: str
    analyzer_run_id: str

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

    failure_reason: str = ""
    profile_name: str = ""
    status: AnalysisStatus = AnalysisStatus.OK
    meta: AnalysisMeta = AnalysisMeta()
