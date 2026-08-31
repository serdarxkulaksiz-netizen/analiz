"""Findings contract — the fixed boundary between Extraction and Prompt Building.

Source-shape independent structure; field names are frozen. Evidence block
labels (plan.md A5) are architectural constants: raw evidence travels as
labeled blocks, interpretation is left to the LLM (parse-minimal).
"""

from pydantic import BaseModel

from app.domain.enums import StepStatus

# Labeled evidence block names (plan.md A6) — contract constants, not config.
# BROWSER LOG = browser.default.log; CONSOLE.LOG = Jenkins console.log (job-level).
#: Written in place of an evidence the profile asked for but that never arrived
#: (or arrived empty), so the gap is visible to the LLM instead of the block
#: silently disappearing from the prompt.
EVIDENCE_UNAVAILABLE = "(bu kanıt alınamadı / bulunmuyor)"

BLOCK_STEPS = "ADIMLAR"
BLOCK_ERROR = "HATA"
BLOCK_DOM = "DOM"
BLOCK_BROWSER = "BROWSER LOG"
BLOCK_CONSOLE = "CONSOLE.LOG"


class Step(BaseModel):
    """One test step and its outcome (plan.md A6 `steps`)."""

    name: str
    status: StepStatus


class EvidenceBlock(BaseModel):
    """A labeled raw-evidence block, rendered as `=== <label> ===` in the prompt."""

    label: str
    content: str


class Findings(BaseModel):
    """Fixed contract between Halka 2 (Extraction) and Halka 3 (Prompt Building).

    UI/DOM content is NOT a separate field — it travels inside
    `evidence_blocks` (e.g. the `=== DOM ===` block), so the contract stays
    source-shape independent.

    `parameter1`/`parameter2` are the generic customization keys from the
    request (user decision superseding plan.md A6 bank/platform): they select
    the analysis profile and are stamped through to the stored result.
    """

    parameter1: str = "default"
    parameter2: str = "default"
    scenario_name: str
    failed_step: str = ""
    error_message: str = ""
    steps: list[Step] = []
    evidence_blocks: list[EvidenceBlock] = []
    screenshot_paths: list[str] = []
    retry_info: str = ""
    # Profile-driven extras: which profile ran, its extra prompt context, and
    # whether content rules actually cut anything (visible, never silent).
    profile_name: str = ""
    extra_context: str = ""
    truncated: bool = False
    truncated_note: str = ""
    # Evidence types the profile keeps out of the store: their inline content is
    # dropped from the `evidence` row (metadata stays, so the gap is visible).
    excluded_from_store: list[str] = []
