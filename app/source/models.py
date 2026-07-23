"""Raw job data models — the Source layer's output (plan.md A4).

Raw, unparsed evidence per failed scenario. Flaky scenarios (failed first,
passed on retry) are NOT included: VisiumGo returns their passing log and
there is nothing to analyze (plan.md A4).
"""

from pydantic import BaseModel

from app.domain.enums import Platform


class RawScenario(BaseModel):
    """One failed scenario's raw evidence bundle (plan.md A4.3).

    Any field may be empty ("missing evidence" is tolerated, A5.4). Typical
    combos: web = test_log + dom_html + browser_log + web_screenshot;
    mobile = test_log + mobile_screenshot; hybrid = web files + mobile
    screenshot + test_log. `platform` is set from the job/request, not guessed.
    """

    scenario_name: str
    platform: Platform
    test_log: str = ""
    dom_html: str = ""
    browser_log: str = ""
    web_screenshot_path: str = ""
    mobile_screenshot_path: str = ""
    retry_info: str = ""


class JobData(BaseModel):
    """A finished job run's report: which scenarios failed, with raw evidence."""

    bank: str
    job_id: str
    platform: Platform
    total_scenario_count: int = 0
    failed_scenarios: list[RawScenario] = []
    # Jenkins console.log: fetch method not yet known (plan.md A4) — the
    # contract slot exists, filled on the work PC.
    jenkins_console_log: str = ""
