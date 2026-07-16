"""Contract-fixed enums (plan.md A6, A8, A11).

These are architectural constants: the *values* are part of the frozen
contracts and must not change (plan.md B3.2).
"""

from enum import Enum


class Platform(str, Enum):
    """Test platform (plan.md A6)."""

    WEB = "web"
    MOBILE = "mobile"
    IOS = "ios"


class Verdict(str, Enum):
    """Action decision produced by the LLM (plan.md A8)."""

    TEST_MAINTENANCE = "test_maintenance"
    APPLICATION_BUG = "application_bug"
    ENVIRONMENT_ERROR = "environment_error"
    TRANSIENT_ERROR = "transient_error"


class StepStatus(str, Enum):
    """Result of a single test step (plan.md A6 `steps`)."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RunStatus(str, Enum):
    """Lifecycle of an analyzer run (plan.md A11 + user-approved addition).

    `failed` = job-level failure (e.g. source unreachable): the run finished
    abnormally, details in the run row's `note`. Scenario-level LLM failures
    do NOT fail the run; they are marked per-row via `analysis_failed`.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
