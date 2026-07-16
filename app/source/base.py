"""Source interface (plan.md Halka 1) — pluggable data origin."""

from abc import ABC, abstractmethod

from app.source.models import JobData


class Source(ABC):
    """Fetches a finished job's failure evidence for a given bank."""

    @abstractmethod
    async def fetch_job(self, bank: str, job_id: str) -> JobData:
        """Return the job report and raw evidence for every failed scenario."""
