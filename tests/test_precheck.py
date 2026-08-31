"""PreCheck tests (plan.md A7): the NoOp hook never short-circuits."""

from app.domain.findings import Findings
from app.precheck.noop import NoOpPreCheck


def test_noop_precheck_always_returns_none() -> None:
    precheck = NoOpPreCheck()
    findings = Findings(scenario_name="S")
    assert precheck.check(findings) is None
