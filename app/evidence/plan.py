"""The profile decision for one run, taken once.

A run's profile answers three questions — which profile is it, which files are
worth downloading, is the job log worth fetching — and all three come from the
same lookup. They used to be asked separately: two planner methods each
resolved the profile again, and the extractor resolved it once more for every
failed scenario. A run with 40 failed scenarios resolved the same profile 42
times. Nothing broke (the answer is deterministic), but "which profile ran" had
42 answers instead of one place holding it.

`plan_for` does the lookup once and hands back an object that carries it. The
service holds that object for the whole run and passes it down.

This module sits below the profile registry and the evidence registry because
it needs both: the profile says WHICH evidence names it wants, and only the
evidence registry can say which name an attachment maps to. Putting `plan_for`
on `ProfileRegistry` would point `profiles.py` at `registry.py`, which already
points back at it.
"""

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
        """Should this attachment be downloaded at all?

        Judged from metadata only — `deviceId`, `mimeType`, `fileName` all
        arrive with the scenario detail — so a file the profile does not want
        costs nothing.

        An attachment no Evidence class claims is ALWAYS fetched: it is the one
        file we cannot judge without looking at it, and the evidence report
        lists it as unclaimed so it can be looked at. Skipping it would hide the
        thing we most want to see — a new device or file type VisiumGo started
        producing.
        """
        name = evidence_name_for(attachment)
        return name in self._wanted if name else True

    @property
    def wants_build_log(self) -> bool:
        """Does this run's profile need the job-level build log?

        The build log has its own endpoint, so it cannot be judged by `wants` —
        but it is the same decision, from the same profile. Fetching it
        unconditionally meant downloading a ZIP for every run whether anything
        read it or not.
        """
        return BuildLogEvidence.evidence_name in self._wanted


def plan_for(profiles: ProfileRegistry, *, job_id: str = "", forced: str = "") -> AnalysisPlan:
    """Resolve the profile for this run — the ONLY place that does."""
    return AnalysisPlan(profiles.get(job_id=job_id, forced=forced))


__all__ = ["AnalysisPlan", "plan_for"]
