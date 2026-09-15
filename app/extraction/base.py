"""Extractor interface.

Raw evidence goes out as labeled blocks; interpretation belongs to the LLM
(parse-minimal).

The `profile` arrives already resolved: which evidence reaches the prompt, in
what order, and how each one is shaped are its decisions. Extraction does not
look a profile up — the run resolved it once, before any evidence was fetched,
and hands the same object to every scenario. The request's
`parameter1`/`parameter2` never reach here: they decide nothing.

`build_log` is job-level context (VisiumGo `/api/runs/{run_id}/logs` ->
`build.log`): it covers the whole run, not one scenario, and becomes a prompt
block when the profile includes `BuildLogEvidence`. `build_log_error` says why
it is missing although the profile asked for it — carried so the evidence row
can answer that on its own, without anyone opening the run row.
"""

from abc import ABC, abstractmethod

from app.domain.findings import Findings
from app.evidence.profiles import Profile
from app.source.models import RawScenario


class Extractor(ABC):
    """Turns one failed scenario's raw evidence into the Findings contract."""

    @abstractmethod
    def extract(
        self,
        scenario: RawScenario,
        *,
        profile: Profile,
        build_log: str = "",
        build_log_error: str = "",
        build_log_path: str = "",
    ) -> Findings:
        """Build Findings (labeled blocks + minimal fields) from raw evidence."""
