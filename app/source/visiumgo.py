"""VisiumGoSource — real VisiumGo API client (STUB).

# TODO(work-pc): implement on the work computer once the real VisiumGo API
# response structure is visible (plan.md A13). Known so far (plan.md A4):
#   - job report lists failed scenarios (e.g. 10 of 100 failed)
#   - attachment URL pattern:
#     .../api/runs/{run_id}/attachments/{attachment_id}/browser.default_{n}.html
#   - flaky scenarios return the *passing* log -> exclude from failed_scenarios
#   - Jenkins console.log comes from a separate API (method still unknown)
"""

from app.domain.enums import Platform
from app.source.banks import BankRegistry
from app.source.base import Source
from app.source.models import JobData


class VisiumGoSource(Source):
    """Fetches real job evidence from a bank's VisiumGo instance (stub)."""

    def __init__(self, registry: BankRegistry) -> None:
        self._registry = registry

    async def fetch_job(self, bank: str, job_id: str, platform: Platform) -> JobData:
        connection = self._registry.get(bank)
        # TODO(work-pc): call the VisiumGo API at connection.visiumgo_base_url,
        # download the job report + per-scenario attachments (test.log,
        # browser.default.log, DOM html, png) and build JobData with raw,
        # unparsed contents. Also fetch the Jenkins console.log once its API
        # is known.
        raise NotImplementedError(
            "VisiumGoSource is a stub; implement on the work PC "
            f"(bank='{connection.name}', job_id='{job_id}'). "
            "Use SOURCE_PROVIDER=mock until then."
        )
