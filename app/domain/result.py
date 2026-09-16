"""Output JSON contract — flat, fixed schema.

`LLMAnalysis` = fields the LLM must return (field names English, text content
Turkish). `AnalysisResult` = the stored row: the same flat fields plus
system-side metadata the code attaches (the LLM never produces these — notably
`profile_name`, which the code attaches, not the model).

No fabricated defaults for text fields: if the LLM leaves a
field out, it stays empty.
"""

from pydantic import BaseModel

from app.domain.enums import AnalysisStatus, Verdict


class AnalysisMeta(BaseModel):
    """System-side call metadata (`meta`)."""

    #: Who produced this diagnosis: `llm` or `precheck` ("" = neither ran).
    #: Separate from `llm_model` because a PreCheck answer has no model, and
    #: writing the word "precheck" into a field that names a model made the
    #: stored row claim a model that never existed.
    answered_by: str = ""
    llm_model: str = ""
    #: Which prompt template was used, and a hash of its exact text. Without
    #: these, "the answers got worse" cannot be traced back to a prompt change
    #: after the fact — the whole reason quality regressions were unprovable.
    prompt_template: str = ""
    prompt_version: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    analyzed_at: str = ""


class LLMAnalysis(BaseModel):
    """Exactly what the LLM is required to return.

    `verdict` and `confidence` are mandatory: if missing or invalid the response
    is rejected and the scenario is marked `analysis_failed`. `confidence` is
    stored as returned — no mapping.

    `scenario_name` is NOT here. The system knows which scenario it asked
    about; asking the model to repeat it meant the stored row took the name
    from the answer — empty when the model left it out, and a different
    scenario's name when the model got it wrong. A fact the system already
    holds is never read back out of the model's mouth.
    """

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

    `scenario_name` is ALWAYS the system's — on every status, not just the
    failed ones. It is the identity of what was analyzed, not part of the
    answer. The request's parameters are not repeated here: they live on the
    run row this result belongs to.
    """

    # --- persistence keys (system) ---
    result_id: str
    analyzer_run_id: str

    # --- LLM fields ---
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

    # --- system-side meta ; code attaches, LLM never produces) ---
    #: Why this row carries no diagnosis, in one sentence, when `status` is not
    #: `ok`. The status alone says THAT something went wrong; this says what,
    #: without anyone opening the trace files to find out.
    failure_reason: str = ""
    profile_name: str = ""  # which analysis profile actually ran
    status: AnalysisStatus = AnalysisStatus.OK
    meta: AnalysisMeta = AnalysisMeta()
