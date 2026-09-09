"""Job-level run state drives the analysis (plan.md A4.0).

`runResult.state` answers "did the JOB run?", not "did the scenarios pass".
Three states, three behaviours, all decided in one place:
  PASSED  -> the normal chain
  FAILED  -> every scenario is analyzed with the fixed `job_failed` profile
  RUNNING -> refused; nothing is fetched, not even the build log
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.evidence.profiles import JOB_FAILED_PROFILE_NAME
from app.main import create_app
from app.source.mock import MockSource
from app.source.models import JobData, RunSummary
from tests.conftest import write_profiles


def _run(app, job_id: str) -> dict:
    """Start a job and read the finished run row from disk (profile included).

    The stored row is read rather than the API view because the diagnosis view
    deliberately does not expose which profile ran — that is trace, not result.
    """
    client = TestClient(app)
    started = client.post("/analyze/visiumgo", json={"job_id": job_id}).json()
    run = app.state.service.get_run(started["analyzer_run_id"])
    assert run is not None
    return run


def test_running_job_is_refused_without_fetching_anything(settings: Settings) -> None:
    """A half-written run must not be diagnosed as if it were finished."""
    app = create_app(settings)
    fetched: list[str] = []

    real_fetch = app.state.service._source.fetch_job

    async def spy(run: RunSummary) -> JobData:
        fetched.append(run.run_id)
        return await real_fetch(run)

    app.state.service._source.fetch_job = spy  # type: ignore[method-assign]

    result = _run(app, "job-7-running")

    assert result["status"] == "failed"
    assert "RUNNING" in result["note"]
    assert result["results"] == []
    assert fetched == []  # not one request was paid for


def test_failed_job_uses_the_fixed_profile_and_says_so(settings: Settings) -> None:
    """When the job itself failed, its own profile describes a run that never happened."""
    result = _run(create_app(settings), "job-7-jobfail")

    assert result["status"] == "done"
    assert JOB_FAILED_PROFILE_NAME in result["note"]
    assert result["results"]
    assert {row["profile_name"] for row in result["results"]} == {JOB_FAILED_PROFILE_NAME}


def test_passed_job_uses_normal_profile_resolution(settings: Settings) -> None:
    result = _run(create_app(settings), "job-7")

    assert result["status"] == "done"
    assert result["note"] == ""
    assert {row["profile_name"] for row in result["results"]} == {"default_web"}


@pytest.mark.asyncio
async def test_mock_source_reports_the_state_before_any_evidence(settings: Settings) -> None:
    """Resolution is cheap and carries the state — that is what the branch reads."""
    source = MockSource()

    assert (await source.resolve_run("job-1")).state == "PASSED"
    assert (await source.resolve_run("job-1-jobfail")).state == "FAILED"
    assert (await source.resolve_run("job-1-running")).state == "RUNNING"

    with pytest.raises(ValueError, match="required"):
        await source.resolve_run("")


class RunIdOnlySource(MockSource):
    """A run reached by run_id alone: the job it belongs to comes from VisiumGo."""

    async def resolve_run(self, job_id: str, run_id: str = "") -> RunSummary:
        summary = await super().resolve_run(job_id or "job-x", run_id)
        return summary.model_copy(update={"job_id": "901"})


def test_run_id_only_request_takes_its_profile_from_the_runs_job(
    settings: Settings, tmp_path
) -> None:
    """With no job_id in the request, the run response says which job it is.

    Without this the caller would have to know the job id to get the job's
    profile, and a run_id-only request would always fall back to `default`.
    """
    profiles = write_profiles(
        tmp_path / "profiles.json",
        {
            "default": {"evidence_to_llm": ["TestLogEvidence"]},
            "job_901": {"job_ids": ["901"], "evidence_to_llm": ["TestLogEvidence"]},
        },
    )
    app = create_app(settings.model_copy(update={"profiles_config_path": profiles}))
    app.state.service._source = RunIdOnlySource()

    client = TestClient(app)
    started = client.post("/analyze/visiumgo", json={"run_id": "RUN_5"}).json()
    run = app.state.service.get_run(started["analyzer_run_id"])

    assert run is not None
    assert {row["profile_name"] for row in run["results"]} == {"job_901"}
