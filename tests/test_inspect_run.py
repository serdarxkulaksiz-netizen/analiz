"""`tools.inspect_run` — the one-command "is the evidence arriving?" check.

The tool exists to be trusted without reading it, so the two promises in its
docstring are tested, not just written: it never calls a real LLM, and its exit
code actually reflects what it printed.
"""

import pytest

from app.config import Settings
from app.llm.provider import LLMProvider, LLMResponse
from tools import inspect_run


class ExplodingLLMProvider(LLMProvider):
    """Stands in for the on-prem model: being called at all is the failure."""

    async def complete(self, prompt: str) -> LLMResponse:  # pragma: no cover - must not run
        raise AssertionError("inspect_run gerçek LLM'e gitti")


@pytest.fixture
def tool_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point the tool at the test settings (mock source, tmp database)."""
    monkeypatch.setattr(inspect_run, "get_settings", lambda: settings)
    return settings


def test_llm_is_never_called(tool_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with a real provider configured, the tool builds the mock one.

    The configured provider is replaced with one that fails on any call, so a
    single request would turn this test red.
    """
    import app.main

    monkeypatch.setitem(
        app.main.LLM_REGISTRY, "openai_compatible", lambda s: ExplodingLLMProvider()
    )
    configured = tool_settings.model_copy(update={"llm_provider": "openai_compatible"})
    monkeypatch.setattr(inspect_run, "get_settings", lambda: configured)

    assert inspect_run._settings_without_llm().llm_provider == "mock"
    assert inspect_run.inspect(run_id="", job_id="job-1") == 0


def test_reports_every_attachment_and_succeeds(
    tool_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = inspect_run.inspect(run_id="", job_id="job-1")
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "KOŞUM" in out and "state=PASSED" in out
    # Every mock attachment shows up, mapped, with its size.
    for name in ("MOCK_test.log", "MOCK_test.properties", "MOCK_mobile.android.samsung.xml"):
        assert name in out
    assert "PROMPT" in out and "SONUÇ: her şey yerinde" in out


def test_running_run_is_reported_as_failure(
    tool_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that is still going cannot be inspected — and says so."""
    exit_code = inspect_run.inspect(run_id="", job_id="job-1-running")

    assert exit_code == 1
    assert "KOŞUM BAŞARISIZ" in capsys.readouterr().out


def test_missing_file_on_disk_is_a_problem(
    tool_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mock's stored paths do not exist, so the tool must not call it clean.

    This is the check that matters on the work PC: a file the API said it sent,
    that is not on disk, is exactly the failure mode we cannot see by eye.
    """
    assert inspect_run._attachment_status({"evidence_name": "TestLogEvidence"}, "") == "EKSİK"
    assert inspect_run._attachment_status({"evidence_name": ""}, "x") == "EŞLEŞMEDİ"
    assert inspect_run._attachment_status({"download_skipped": True}, "") == "ATLANDI"
    # The job-level build log has no file of its own — that is not a problem.
    assert inspect_run._attachment_status({"device_id": "build"}, "") == "JOB LOGU"


def test_needs_a_run_or_a_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["inspect_run"])
    monkeypatch.setattr(inspect_run, "DEFAULT_RUN_ID", "")
    monkeypatch.setattr(inspect_run, "DEFAULT_JOB_ID", "")

    with pytest.raises(SystemExit):
        inspect_run.main()
