"""The profile decision for one run, taken once."""

from app.evidence.profiles import Profile, ProfileRegistry
from app.evidence.registry import evidence_name_for
from app.evidence.types import BuildLogEvidence
from app.source.models import Attachment


class AnalysisPlan:
    """One run's resolved profile, plus what it wants fetched."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self._wanted = set(profile.evidence_to_llm)

    def wants(self, attachment: Attachment) -> bool:
        """Should this attachment be downloaded at all?

        A file that maps to no evidence class is not downloaded either: nothing
        would read it, and the profile's list is the whole answer to "what do we
        fetch". It is still reported, flagged as skipped.
        """
        return evidence_name_for(attachment) in self._wanted

    @property
    def wants_build_log(self) -> bool:
        """Does this run's profile need the job-level build log?"""
        return BuildLogEvidence.evidence_name in self._wanted


def plan_for(profiles: ProfileRegistry, *, profil: str = "", forced: str = "") -> AnalysisPlan:
    """Resolve the profile for this run — the ONLY place that does."""
    return AnalysisPlan(profiles.get(name=profil, forced=forced))


__all__ = ["AnalysisPlan", "plan_for"]
