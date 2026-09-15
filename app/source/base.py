"""Source interface — pluggable data origin."""

from abc import ABC, abstractmethod
from typing import Protocol

from app.source.models import Attachment, JobData, RunSummary


class DownloadPlan(Protocol):
    """What this layer needs in order to decide what to fetch.

    Declared HERE, by the layer that asks the questions — not imported from the
    layer that answers them. That is what keeps the source ignorant: it never
    learns what a profile or an Evidence class is, it just asks "do you want
    this file?" and "do you want the job log?" of whatever it was handed.

    Two questions instead of two arguments: a third one ("does the profile want
    the screenshots inlined?", say) becomes a member here, not another
    parameter on `fetch_job` and every call site of it.
    """

    def wants(self, attachment: Attachment) -> bool:
        """Should this attachment be downloaded at all?"""
        ...

    @property
    def wants_build_log(self) -> bool:
        """Should the job-level log endpoint be called?"""
        ...


class FetchEverything:
    """A plan that takes every file there is — what the source did before profiles.

    Not used in production: a real run always arrives with a resolved profile.
    It exists so a caller that genuinely wants everything (and a test about the
    source alone) does not have to invent one.
    """

    def wants(self, attachment: Attachment) -> bool:
        return True

    @property
    def wants_build_log(self) -> bool:
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
        — and decide how to treat the run — before paying for the (expensive)
        evidence download. `run_id` wins over `job_id`; raises if neither is
        given.

        A named `run_id` resolves to THAT run whatever its state; a `job_id`
        picks the newest FINISHED run, because choosing one on the caller's
        behalf is a judgement and an unfinished run is the wrong answer to it.
        """

    @abstractmethod
    async def fetch_job(self, run: RunSummary, plan: DownloadPlan) -> JobData:
        """Return the job report and raw evidence for every failed scenario.

        Takes the already-resolved run: resolution happens once, in
        `resolve_run`, so the run summary is never fetched twice. It takes the
        already-resolved plan for the same reason.

        Every decision the plan makes is taken from metadata, BEFORE any bytes
        are transferred. A file the plan rejects is still reported (metadata +
        `download_skipped`), so "the profile did not want it" and "it never
        arrived" stay distinguishable.
        """
