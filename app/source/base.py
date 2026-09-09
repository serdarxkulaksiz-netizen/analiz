"""Source interface (plan.md Halka 1) — pluggable data origin."""

from abc import ABC, abstractmethod

from app.source.models import JobData, RunSummary


class Source(ABC):
    """Fetches a finished job's failure evidence.

    Note: the request's parameter1/parameter2 do NOT reach the source — they
    only customize the analysis side (profiles). The source is identified by
    job_id/run_id alone (single VisiumGo instance, connection from .env).
    """

    @abstractmethod
    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        """Resolve WHICH run to analyze — cheap, no evidence fetched.

        Separate from `fetch_job` so the caller can check its cache and read
        the job-level `state` before paying for the (expensive) evidence
        download. `run_id` wins over `job_id`; raises if neither is given.
        """

    @abstractmethod
    async def fetch_job(self, run: RunSummary) -> JobData:
        """Return the job report and raw evidence for every failed scenario.

        Takes the already-resolved run: resolution happens once, in
        `resolve_run`, so the run summary is never fetched twice.
        """
