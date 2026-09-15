"""Error-resilience tests: a bad LLM never kills the job."""

import pytest

from app.config import Settings
from app.domain.api import build_run_view
from app.evidence.planner import AttachmentPlanner
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.llm.mock import MockLLMProvider
from app.llm.provider import LLMError, LLMProvider, LLMResponse
from app.persistence.file_repository import FileRepository
from app.precheck.noop import NoOpPreCheck
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.base import AttachmentFilter, Source, accept_all
from app.source.mock import MockSource
from app.source.models import JobData, RawScenario, RunSummary


class GarbageLLMProvider(LLMProvider):
    """Returns non-JSON garbage."""

    async def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(content="ÜZGÜNÜM, bugün analiz yapamıyorum!!!", model="garbage")


class TimeoutLLMProvider(LLMProvider):
    """Simulates a transport failure/timeout."""

    async def complete(self, prompt: str) -> LLMResponse:
        raise LLMError("ReadTimeout: simulated")


def _service(settings: Settings, llm: LLMProvider) -> AnalyzerService:
    profiles = ProfileRegistry(settings.profiles_config_path)
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=MockSource(),
        extractor=EvidenceExtractor(EvidenceRegistry(), profiles),
        prompt_builder=PromptBuilder(settings.prompts_dir, settings.confidence_buckets),
        llm_provider=llm,
        precheck=NoOpPreCheck(),
        planner=AttachmentPlanner(profiles),
    )


@pytest.mark.asyncio
async def test_garbage_llm_marks_scenarios_failed_but_job_finishes(
    settings: Settings,
) -> None:
    service = _service(settings, GarbageLLMProvider())
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"
    assert run["completed_count"] == run["scenario_count"] == 2
    for result in run["results"]:
        assert result["status"] == "analysis_failed"
        assert result["verdict"] is None
        assert "ÜZGÜNÜM" in result["raw_llm_response"]  # raw answer kept
        assert result["explanation"] == ""  # no fabricated default text
        assert result["scenario_name"]  # identity still traceable


@pytest.mark.asyncio
async def test_llm_timeout_marks_scenarios_failed_but_job_finishes(
    settings: Settings,
) -> None:
    service = _service(settings, TimeoutLLMProvider())
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"
    for result in run["results"]:
        assert result["status"] == "analysis_failed"
        assert "ReadTimeout" in result["raw_llm_response"]


class FailingSource(Source):
    """A source whose fetch fails (e.g. VisiumGo unreachable / auth error)."""

    async def resolve_run(self, job_id, run_id=""):  # type: ignore[no-untyped-def]
        return RunSummary(run_id=run_id or f"RUN_{job_id}", job_id=job_id, state="PASSED")

    async def fetch_job(self, run, wants=accept_all):  # type: ignore[no-untyped-def]
        raise RuntimeError("VisiumGo unreachable")


@pytest.mark.asyncio
async def test_source_failure_finishes_run_with_note(settings: Settings) -> None:
    profiles = ProfileRegistry(settings.profiles_config_path)
    service = AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=FailingSource(),
        extractor=EvidenceExtractor(EvidenceRegistry(), profiles),
        prompt_builder=PromptBuilder(settings.prompts_dir, settings.confidence_buckets),
        llm_provider=GarbageLLMProvider(),
        precheck=NoOpPreCheck(),
        planner=AttachmentPlanner(profiles),
    )
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "failed"
    assert "job failed" in run["note"]


class BrokenResultsRepository(FileRepository):
    """A repository whose `analysis_results` writes fail (disk full / permission).

    Those writes sit OUTSIDE `_analyze_scenario`'s try block, so the failure
    escapes into `asyncio.gather` — the exact path that used to be swallowed.
    """

    def save(self, table: str, row_id: str, data: dict) -> None:  # type: ignore[override]
        if table.endswith("analysis_results"):
            raise OSError("disk dolu")
        super().save(table, row_id, data)


@pytest.mark.asyncio
async def test_persistence_failure_is_reported_not_swallowed(settings: Settings) -> None:
    """A scenario that cannot be saved must leave a trace, not vanish.

    Regression: `gather(..., return_exceptions=True)` discarded these, so the
    run reported `done` with missing results and no explanation anywhere.
    """
    service = _service(settings, MockLLMProvider(settings.llm_model))
    service._repo = BrokenResultsRepository(settings.database_dir)
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"  # the job still finishes
    assert run["completed_count"] == 0  # nothing was actually completed
    assert "kaydedilemedi" in run["note"]  # and it says so
    assert "disk dolu" in run["note"]  # naming the real cause
    assert run["results"] == []


class BuildLogFailingSource(MockSource):
    """Mock evidence, but the job-level build log could not be fetched.

    Mirrors a misconfigured/failing `/logs` endpoint: the scenarios arrive
    normally, only the build log is missing — and it says why.
    """

    async def fetch_job(
        self,
        run: RunSummary,
        wants: AttachmentFilter = accept_all,
        *,
        want_build_log: bool = False,
    ) -> JobData:
        job = await super().fetch_job(run, wants, want_build_log=want_build_log)
        return job.model_copy(
            update={
                "build_log": "",
                "build_log_error": (
                    "/api/runs/RUN_1/logs: HTTPStatusError: "
                    "Client error '404 Not Found' for url ..."
                ),
            }
        )


@pytest.mark.asyncio
async def test_missing_build_log_reports_its_reason(settings: Settings) -> None:
    """A build log that could not be fetched must not look like "there was none".

    Both cases leave `build_log` empty, so without a recorded reason a broken
    endpoint is indistinguishable from a deliberately unconfigured one.
    """
    service = _service(settings, MockLLMProvider(settings.llm_model))
    service._source = BuildLogFailingSource()
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    # The job is untouched by this: it still finishes and still analyzes.
    assert run["status"] == "done"
    assert run["completed_count"] == run["scenario_count"] == 2
    # But the missing log now carries its cause, on disk and in the API view.
    assert run["build_log_chars"] == 0
    assert run["build_log_path"] == ""
    assert "404" in run["build_log_error"]
    assert "404" in build_run_view(run).build_log_error


class CountingLLMProvider(LLMProvider):
    """Records whether the LLM was called at all."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content="{}", model="counting")


class NoEvidenceSource(MockSource):
    """A run whose failed scenario produced nothing: no error text, no files."""

    async def fetch_job(
        self,
        run: RunSummary,
        wants: AttachmentFilter = accept_all,
        *,
        want_build_log: bool = False,
    ) -> JobData:
        job = await super().fetch_job(run, wants, want_build_log=want_build_log)
        bare = RawScenario(scenario_name="MOCK_kanıtsız senaryo")
        return job.model_copy(update={"failed_scenarios": [bare], "build_log": ""})


@pytest.mark.asyncio
async def test_scenario_without_any_evidence_never_reaches_the_llm(
    settings: Settings,
) -> None:
    """An empty prompt buys an answer the system already knows ("kanıt yok").

    So the call is skipped and the outcome says exactly that — distinct from
    `analysis_failed`, where something actually broke.
    """
    llm = CountingLLMProvider()
    service = _service(settings, llm)
    service._source = NoEvidenceSource()
    run_id = service.create_run("default", "job-1", "default")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"  # the job still finishes cleanly
    assert llm.calls == 0  # no call was paid for
    (result,) = run["results"]
    assert result["status"] == "no_evidence"
    assert result["verdict"] is None  # no fabricated diagnosis
    assert result["explanation"] == ""
    assert result["scenario_name"] == "MOCK_kanıtsız senaryo"
