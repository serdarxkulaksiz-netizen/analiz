"""Findings contract — the fixed boundary between Extraction and Prompt Building.

Source-shape independent structure; field names are frozen. Raw evidence
travels as labeled blocks, one per file; interpretation is left to the LLM
(parse-minimal).
"""

from pydantic import BaseModel

#: Prompt template used when a profile does not name its own.
#: Lives here, in the contract layer, because both the profile config and the
#: prompt builder need it without depending on each other.
DEFAULT_PROMPT_TEMPLATE = "default"


class EvidenceBlock(BaseModel):
    """One evidence, rendered as `=== <label> ===` + content in the prompt.

    `label` names the FILE it came from plus what that file is, e.g.
    `test.log · koşum logu: build çıktısı, adımlar ve sonuçları`. The file name
    is the one VisiumGo's UI shows, so a person and the model are looking at
    the same thing; the description is there because a bare `browser.default.log`
    does not tell the model it is a browser console.

    `evidence_name` is the Evidence class behind it — how a template finds this
    block for its own placeholder (labels vary per run, class names do not).
    """

    label: str
    content: str
    evidence_name: str = ""


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
    #: Why the download failed, when it did. The third reason `chars` can be 0,
    #: and the only one that is a fault.
    download_error: str = ""
    #: Size of the text taken inline (before content rules). Always 0 for a
    #: binary file: its bytes are on disk, not in this record.
    chars: int = 0
    #: Where the downloaded file landed. This is the ONLY record of that now —
    #: the raw scenario dump that used to carry it is gone, along with the
    #: second copy of every text file it took with it.
    stored_path: str = ""


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


class JobLogReport(BaseModel):
    """The job-level build log as extraction saw it.

    Deliberately NOT an `AttachmentReport`: the build log does not arrive in
    VisiumGo's `attachments[]` array at all — it comes from its own endpoint.
    Putting it in that list would mean the report claims the API sent a file it
    never sent, which is the one thing this report exists to answer honestly.
    """

    #: Where it comes from, so nobody has to remember that it is not an attachment.
    source: str = "/api/runs/{run_id}/logs"
    #: Did the active profile ask for it at all? False = never fetched.
    wanted: bool = False
    #: Size as received (before content rules).
    chars: int = 0
    goes_to_llm: bool = False
    goes_to_store: bool = False
    #: Why it is missing although the profile wanted it (network, 404, not a
    #: ZIP, entry missing). Empty when it was not wanted or it arrived.
    error: str = ""


class EvidenceReport(BaseModel):
    """Extraction's self-diagnosis for one scenario.

    Stored with the raw evidence so one real run answers "why was the prompt
    empty / oversized?" without anyone reproducing it by hand.
    """

    #: ONLY what VisiumGo's `attachments[]` array carried. Nothing this code
    #: produced ever enters this list.
    attachments: list[AttachmentReport] = []
    #: The job-level build log — a separate endpoint, so a separate field.
    job_log: JobLogReport = JobLogReport()
    #: Why this scenario's detail call never happened or failed. When it is
    #: set, `attachments` is empty for a reason that has nothing to do with the
    #: run producing no files.
    scenario_error: str = ""
    #: Content rules that could not do what the profile asked. The evidence
    #: they were shaping produces NO block: a rule that failed has not trimmed
    #: anything, and sending the untrimmed original would be the silent
    #: behaviour this replaces.
    rule_errors: list[str] = []
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
    part in any decision the code makes. Nothing that cannot
    influence the analysis belongs in the analysis contract.

    The scenario's `errorText` and `stepResults` are absent for a different
    reason: VisiumGo derives both by parsing `test.log`, which the profile
    sends whole. Carrying them here meant shipping the same information twice.
    """

    scenario_name: str
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
    #: What extraction saw and did (observability, never sent to the LLM).
    evidence_report: EvidenceReport = EvidenceReport()

    @property
    def has_evidence_for_llm(self) -> bool:
        """True if there is anything for the model to reason about.

        The prompt now carries evidence blocks and nothing else, so this is
        simply "did any block arrive with content in it". An empty prompt would
        buy an answer the system already knows ("kanıt yok").
        """
        return any(block.content for block in self.evidence_blocks)
