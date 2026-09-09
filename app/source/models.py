"""Raw job data models — the Source layer's output.

Attachment-based, source-agnostic shape: both MockSource and VisiumGoSource
produce the SAME `RawScenario`, so the extraction ring is identical regardless
of origin (the mock/real difference lives entirely in the Source).

Everything the source received is kept (user rule: save everything for now):
`raw_detail` carries the scenario-detail response untouched, and
`raw_results_response` / `raw_run_response` carry the job-level responses.
"""

from pathlib import PurePosixPath

from pydantic import BaseModel


class Attachment(BaseModel):
    """One raw file attached to a scenario.

    `device_id` + file extension identify what it is — that pair is exactly the
    label VisiumGo's own UI shows (`browser.default.html`, `test.properties`),
    and it is what the Evidence registry maps. `mime_type` alone is NOT enough:
    `test.log` and `test.properties` are both `text/plain` on the same device.

    Text files (html/xml/logs) carry `content`; binary files (png) carry only
    `stored_path` (where the download was saved), `content` stays empty.
    """

    file_name: str
    mime_type: str
    device_id: str
    content: str = ""
    stored_path: str = ""
    #: True when the active profile did not ask for this evidence, so the file
    #: was never downloaded. Metadata still travels: a file we deliberately did
    #: not fetch must not look like one that failed to arrive.
    download_skipped: bool = False

    @property
    def extension(self) -> str:
        """Lower-cased file extension including the dot ("" if there is none).

        `file_name` arrives as a path with a run-scoped folder and a uniqueness
        number (`-1643527934/mobile.ios.iPhone 13 Pro Max_779188588.png`), so
        the suffix is taken with POSIX path semantics, not by splitting on ".".
        """
        return PurePosixPath(self.file_name).suffix.lower()

    @property
    def label(self) -> str:
        """`<device_id><extension>` — the same name VisiumGo's UI shows.

        Used both to map the attachment to an Evidence class and to name the
        file on disk, so what we store is what a person sees in VisiumGo.
        """
        return f"{self.device_id}{self.extension}"


class RawScenario(BaseModel):
    """One failed scenario's raw evidence bundle.

    Any attachment may be absent; the analysis tolerates whatever arrived.
    `raw_detail` is the FULL scenario-detail API response (properties and all),
    persisted for observability — nothing from the source is thrown away.

    `error_text` arrives with the detail call and is kept here but goes nowhere
    else: it never reaches the prompt, because VisiumGo derives it from
    `test.log` — which the profile sends whole. Its future reader is PreCheck,
    which will look at it BEFORE any attachment is downloaded and may decide
    the scenario needs no analysis at all. The step list is not kept for the
    same reason and has no such future reader.
    """

    scenario_name: str
    scenario_id: str = ""
    error_text: str = ""
    attachments: list[Attachment] = []
    retry_info: str = ""
    raw_detail: dict = {}


class RunSummary(BaseModel):
    """Which run will be analyzed, resolved BEFORE any evidence is fetched.

    Both request shapes converge here: an explicit `run_id` is looked up with
    `GET /api/runs/{run_id}`, a `job_id` picks its newest analyzable run from
    `GET /api/runs?jobId=`. `state` is the job-level health that decides how
    (or whether) the run is analyzed at all — see `RunState`.

    `note` carries anything that was skipped while resolving (e.g. a run with
    a state we do not know), so a skip is never silent.
    """

    run_id: str
    job_id: str = ""
    job_name: str = ""
    state: str = ""
    run_result: dict = {}
    #: The raw run response this summary was built from (save-everything).
    raw: dict = {}
    note: str = ""


class JobData(BaseModel):
    """A finished job run's report: which scenarios failed, with raw evidence."""

    job_id: str = ""
    run_id: str = ""
    job_name: str = ""
    run_result: dict = {}  # state / totals summary (raw, from VisiumGo)
    total_scenario_count: int = 0
    failed_scenarios: list[RawScenario] = []
    # Job-level build log (VisiumGo `/logs` -> `build.log`); empty when the
    # endpoint is not configured.
    build_log: str = ""
    # Why `build_log` is empty when it should NOT be. An unset endpoint is a
    # deliberate skip and leaves this empty as well; a failed fetch (404,
    # timeout, not a ZIP, entry missing) records its reason here. The job
    # continues either way — the reason is carried, never raised.
    build_log_error: str = ""
    # Raw job-level responses for observability.
    raw_run_response: dict = {}
    raw_results_response: list = []
