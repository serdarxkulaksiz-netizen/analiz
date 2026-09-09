"""Source interface (plan.md Halka 1) — pluggable data origin."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.source.models import Attachment, JobData, RunSummary

#: "Should this attachment be downloaded?" — decided by the caller from the
#: active profile, applied here. The source stays ignorant of Evidence classes;
#: it is handed a predicate and asks it, nothing more.
AttachmentFilter = Callable[[Attachment], bool]


def accept_all(attachment: Attachment) -> bool:
    """Default filter: fetch everything (what the source did before profiles)."""
    return True


class Source(ABC):
    """Fetches a finished job's failure evidence.

    Note: the request's parameter1/parameter2 do NOT reach the source — they
    only customize the analysis side (profiles). The source is identified by
    job_id/run_id alone (single VisiumGo instance, connection from .env).
    """

    @abstractmethod
    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Resolve WHICH run to analyze — cheap, no evidence fetched.

        Separate from `fetch_job` so the caller can read the job-level `state`
        — and decide whether there is anything to analyze — before paying for
        the (expensive) evidence download. `run_id` wins over `job_id`; raises
        if neither is given.
        """

    @abstractmethod
    async def fetch_job(self, run: RunSummary, wants: AttachmentFilter = accept_all) -> JobData:
        """Return the job report and raw evidence for every failed scenario.

        Takes the already-resolved run: resolution happens once, in
        `resolve_run`, so the run summary is never fetched twice.

        `wants` decides, from the attachment's metadata and BEFORE any bytes are
        transferred, whether a file is downloaded at all. A file it rejects is
        still reported (metadata + `download_skipped`), so "the profile did not
        want it" and "it never arrived" stay distinguishable.
        """
