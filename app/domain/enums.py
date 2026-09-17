"""Contract-fixed enums."""

from enum import Enum


class Verdict(str, Enum):
    """Action decision produced by the LLM — 6 values."""

    TEST_MAINTENANCE = "test_maintenance"
    APPLICATION_BUG = "application_bug"
    ENVIRONMENT_ERROR = "environment_error"
    TRANSIENT_ERROR = "transient_error"
    UNKNOWN = "unknown"
    INCONCLUSIVE = "inconclusive"


class RunStatus(str, Enum):
    """Lifecycle of an analyzer run (+ user-approved 4th value)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RunState(str, Enum):
    """VisiumGo's JOB-level health for one run (`runResult.state`)."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


ANALYZABLE_RUN_STATES = frozenset({RunState.PASSED.value, RunState.FAILED.value})


class AnalysisStatus(str, Enum):
    """Per-scenario diagnosis outcome (system-side `status`)."""

    OK = "ok"
    ANALYSIS_FAILED = "analysis_failed"
    NO_EVIDENCE = "no_evidence"
