"""Contract-fixed enums (plan.md A6, A10, A13).

These are architectural constants: the *values* are part of the frozen
contracts and must not change (plan.md B3.2).
"""

from enum import Enum


class Verdict(str, Enum):
    """Action decision produced by the LLM (plan.md A10) — 6 values."""

    TEST_MAINTENANCE = "test_maintenance"
    APPLICATION_BUG = "application_bug"
    ENVIRONMENT_ERROR = "environment_error"
    TRANSIENT_ERROR = "transient_error"
    UNKNOWN = "unknown"  # model could say nothing / no evidence
    INCONCLUSIVE = "inconclusive"  # model looked but reached no single verdict


class StepStatus(str, Enum):
    """Result of a single test step (plan.md A6 `steps`)."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RunStatus(str, Enum):
    """Lifecycle of an analyzer run (plan.md A13 + user-approved 4th value).

    plan.md A13 lists pending/running/done; `failed` is a user-approved
    addition for job-level failure (e.g. source unreachable): the run finished
    abnormally, details in the run row's `note`. Scenario-level LLM failures do
    NOT fail the run; they are marked per-row via `AnalysisStatus.ANALYSIS_FAILED`.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RunState(str, Enum):
    """VisiumGo's JOB-level health for one run (`runResult.state`).

    Not the scenarios' health: a run whose `state` is `PASSED` can still carry
    failed scenarios (observed: `state=PASSED` with `failScenarios=2`). It
    answers "did the job itself run to completion?", which is why `FAILED`
    routes every scenario to one fixed profile instead of the job_ids mapping.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


#: States whose run may be analyzed. A `RUNNING` run is deliberately absent:
#: it is still producing evidence, so analyzing it would judge half a run.
#: Any other value (a state VisiumGo adds later) is unknown to us and is
#: skipped as well — but never silently: the skip is recorded on the run row.
ANALYZABLE_RUN_STATES = frozenset({RunState.PASSED.value, RunState.FAILED.value})


class AnalysisStatus(str, Enum):
    """Per-scenario diagnosis outcome (plan.md A10 system-side `status`)."""

    OK = "ok"
    ANALYSIS_FAILED = "analysis_failed"
    #: No evidence at all reached the prompt, so the LLM was never called
    #: (distinct from a failed analysis: nothing broke, there was nothing to
    #: analyze). See `Findings.has_evidence_for_llm`.
    NO_EVIDENCE = "no_evidence"
