"""Download planning — which attachments this run needs at all.

The Source knows how to fetch files; it must not know what an Evidence is. So
the decision "is this file wanted?" is built here, from the active profile, and
injected into `Source.fetch_job` as a plain predicate. That keeps the layering
one-way (evidence -> source models, never the reverse) and keeps the rule in
the one place that already owns profiles.

An attachment no Evidence class claims is ALWAYS fetched: it is the one file we
cannot judge without looking at it, and `inspect_run` / `evidence_report` exist
precisely to surface those. Skipping it would hide the thing we most want to
see (a new device or file type VisiumGo started producing).
"""

from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import evidence_name_for
from app.evidence.types import BuildLogEvidence
from app.source.base import AttachmentFilter
from app.source.models import Attachment


class AttachmentPlanner:
    """Turns the active profile into a "should this file be downloaded?" filter."""

    def __init__(self, profiles: ProfileRegistry) -> None:
        self._profiles = profiles

    def wants_for(self, *, job_id: str = "", forced: str = "") -> AttachmentFilter:
        """Filter for the profile this run resolves to (same order as extraction)."""
        profile = self._profiles.get(job_id=job_id, forced=forced)
        wanted = profile.wanted_evidence

        def wants(attachment: Attachment) -> bool:
            name = evidence_name_for(attachment)
            return name in wanted if name else True  # unknown file: always fetch

        return wants

    def wants_build_log(self, *, job_id: str = "", forced: str = "") -> bool:
        """Does this run's profile need the job-level build log?

        The build log has its own endpoint, so it cannot be judged by the
        attachment filter — but it is the same decision, taken from the same
        profile. Fetching it unconditionally meant downloading a ZIP for every
        run whether anything read it or not.
        """
        profile = self._profiles.get(job_id=job_id, forced=forced)
        return BuildLogEvidence.evidence_name in profile.wanted_evidence


__all__ = ["AttachmentPlanner"]
