"""Findings contract — the fixed boundary between Extraction and Prompt Building.

Source-shape independent structure; field names are frozen. Evidence block
labels (plan.md A5) are architectural constants: raw evidence travels as
labeled blocks, interpretation is left to the LLM (parse-minimal).
"""

from pydantic import BaseModel

from app.domain.enums import StepStatus

# Labeled evidence block names (plan.md A6) — contract constants, not config.
# BROWSER LOG = browser.default.log; BUILD LOG = VisiumGo /logs -> build.log (job-level).
#
# An evidence that did not arrive produces NO block at all: it leaves the prompt
# together with its header (plan.md A5.4). There used to be a
# "(bu kanıt alınamadı)" placeholder so the gap stayed visible; it was dropped
# because a header with a marker under it is still noise the model has to reason
# about, and the prompt then had to spend a paragraph explaining the marker.

#: Prompt template used when a profile does not name its own (plan.md A8).
#: Lives here, in the contract layer, because both the profile config and the
#: prompt builder need it without depending on each other.
DEFAULT_PROMPT_TEMPLATE = "default"

BLOCK_STEPS = "ADIMLAR"
BLOCK_ERROR = "HATA"
BLOCK_DOM = "DOM"
BLOCK_MOBILE_DOM = "MOBIL DOM"
BLOCK_BROWSER = "BROWSER LOG"
BLOCK_BUILD = "BUILD LOG"
BLOCK_TEST_PROPERTIES = "TEST PROPERTIES"


class Step(BaseModel):
    """One test step and its outcome (plan.md A6 `steps`)."""

    name: str
    status: StepStatus


class EvidenceBlock(BaseModel):
    """A labeled raw-evidence block, rendered as `=== <label> ===` in the prompt."""

    label: str
    content: str


class AttachmentReport(BaseModel):
    """One attachment as extraction saw it — did it map to an Evidence class?

    Written for a single question that used to be unanswerable after the fact:
    "did the DOM not arrive, or did it arrive and fail to match?" An unmatched
    attachment (`evidence_name == ""`) means VisiumGo sent a file whose
    mime_type/device_id no Evidence claims.
    """

    file_name: str = ""
    mime_type: str = ""
    device_id: str = ""
    #: Evidence class this mapped to; "" = no class matched.
    evidence_name: str = ""
    #: Whether the active profile sends this evidence to the LLM.
    goes_to_llm: bool = False
    #: True when the profile wanted neither to prompt nor to store this file,
    #: so it was never fetched. Distinguishes "we chose not to" from "it did
    #: not arrive" — both leave `chars` at 0.
    download_skipped: bool = False
    #: Size as received (before content rules).
    chars: int = 0


class BlockReport(BaseModel):
    """One prompt block as it left extraction.

    `available=False` means the block reached the prompt empty (so it was left
    out). `trimmed=False` with a huge `chars` on a job-level log is the signal
    that a slicing rule found no marker and kept everything.
    """

    label: str = ""
    chars: int = 0
    available: bool = False
    trimmed: bool = False


class EvidenceReport(BaseModel):
    """Extraction's self-diagnosis for one scenario (plan.md A0.4).

    Stored with the raw evidence so one real run answers "why was the prompt
    empty / oversized?" without anyone reproducing it by hand.
    """

    attachments: list[AttachmentReport] = []
    blocks: list[BlockReport] = []
    #: File names VisiumGo sent that no Evidence class claimed.
    unmatched: list[str] = []
    #: File names the active profile did not ask for (never downloaded).
    skipped: list[str] = []


class Findings(BaseModel):
    """Fixed contract between Halka 2 (Extraction) and Halka 3 (Prompt Building).

    UI/DOM content is NOT a separate field — it travels inside
    `evidence_blocks` (e.g. the `=== DOM ===` block), so the contract stays
    source-shape independent.

    The request's `parameter1`/`parameter2` are deliberately ABSENT: they are
    reserved keys, recorded on the run and shown by the API, and they take no
    part in any decision the code makes (plan.md A4.2). Nothing that cannot
    influence the analysis belongs in the analysis contract.
    """

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
    #: Which prompt template this scenario is asked with (profile decision).
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE
    extra_context: str = ""
    truncated: bool = False
    truncated_note: str = ""
    # Evidence types the profile keeps out of the store: their inline content is
    # dropped from the `evidence` row (metadata stays, so the gap is visible).
    excluded_from_store: list[str] = []
    #: What extraction saw and did (observability, never sent to the LLM).
    evidence_report: EvidenceReport = EvidenceReport()

    @property
    def has_evidence_for_llm(self) -> bool:
        """True if there is anything for the model to reason about.

        False means every block is empty AND there is no error message or step
        list. Asking the LLM then costs a call to be told "kanıt yok" — which
        the system already knows.
        """
        if self.error_message.strip() or self.steps:
            return True
        return any(block.content for block in self.evidence_blocks)
