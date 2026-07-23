"""Contract-fixed enums (plan.md A6, A10, A13).

These are architectural constants: the *values* are part of the frozen
contracts and must not change (plan.md B3.2).
"""

from enum import Enum


class Platform(str, Enum):
    """Test platform — comes as INPUT, never guessed (plan.md A4.2).

    `hybrid` = a single scenario with both web and mobile steps (e.g. a web
    transaction triggers a phone push, approved on the device, back to web).
    """

    WEB = "web"
    MOBILE = "mobile"
    HYBRID = "hybrid"


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


class AnalysisStatus(str, Enum):
    """Per-scenario diagnosis outcome (plan.md A10 system-side `status`)."""

    OK = "ok"
    ANALYSIS_FAILED = "analysis_failed"
