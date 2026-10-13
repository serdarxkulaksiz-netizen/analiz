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
    #: VisiumGo's own id for this scenario. The NAME is not an identity: two
    #: examples of one Scenario Outline carry the same name, and matching rows
    #: by name would treat them as one scenario.
    scenario_id: str = ""
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
    #: The scenario's own error message, as the source reported it. Not the
    #: model's words: it is what the run itself said went wrong.
    error_text: str = ""
    #: The step the scenario died on — the other half of the grouping key.
    failed_step: str = ""
    #: Set when this diagnosis was produced for ANOTHER scenario with the same
    #: step and error, and copied here. Empty means this scenario was analyzed.
    grouped_with: str = ""
    status: AnalysisStatus = AnalysisStatus.OK
    meta: AnalysisMeta = AnalysisMeta()
