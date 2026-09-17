"""The profile decision for one run, taken once."""

from app.evidence.profiles import Profile, ProfileRegistry
from app.evidence.registry import evidence_name_for
from app.evidence.types import BuildLogEvidence
from app.source.models import Attachment


class AnalysisPlan:
    """One run's resolved profile, plus what it wants fetched."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self._wanted = profile.wanted_evidence

    def wants(self, attachment: Attachment) -> bool:
        """Should this attachment be downloaded at all?"""
        name = evidence_name_for(attachment)
        return name in self._wanted if name else True

    @property
    def wants_build_log(self) -> bool:
        """Does this run's profile need the job-level build log?"""
        return BuildLogEvidence.evidence_name in self._wanted


def plan_for(profiles: ProfileRegistry, *, job_id: str = "", forced: str = "") -> AnalysisPlan:
    """Resolve the profile for this run — the ONLY place that does."""
    return AnalysisPlan(profiles.get(job_id=job_id, forced=forced))


__all__ = ["AnalysisPlan", "plan_for"]
