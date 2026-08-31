"""Source interface (plan.md Halka 1) — pluggable data origin."""

from abc import ABC, abstractmethod

from app.source.models import JobData


class Source(ABC):
    """Fetches a finished job's failure evidence.

    Note: the request's parameter1/parameter2 do NOT reach the source — they
    only customize the analysis side (profiles). The source is identified by
    job_id/run_id alone (single VisiumGo instance, connection from .env).
    """

    @abstractmethod
    async def resolve_run_id(self, job_id: str, run_id: str = "") -> str:
        """Resolve which run to analyze — cheap, no evidence fetched.

        Separate from `fetch_job` so the caller can look the run up in its
        cache before paying for the full download. `run_id` is returned as-is
        when given (no network call at all); otherwise the newest run of
        `job_id` is resolved. Raises if neither is given.
        """

    @abstractmethod
    async def fetch_job(self, job_id: str, run_id: str = "") -> JobData:
        """Return the job report and raw evidence for every failed scenario.

        Either `job_id` or `run_id` identifies the run (`run_id` wins if both
        are given).
        """
