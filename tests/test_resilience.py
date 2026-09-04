"""Error-resilience tests (plan.md A9): a bad LLM never kills the job."""

import pytest

from app.config import Settings
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.llm.mock import MockLLMProvider
from app.llm.provider import LLMError, LLMProvider, LLMResponse
from app.persistence.file_repository import FileRepository
from app.precheck.noop import NoOpPreCheck
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.base import Source
from app.source.mock import MockSource


class GarbageLLMProvider(LLMProvider):
    """Returns non-JSON garbage."""

    async def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(content="ÜZGÜNÜM, bugün analiz yapamıyorum!!!", model="garbage")


class TimeoutLLMProvider(LLMProvider):
    """Simulates a transport failure/timeout."""

    async def complete(self, prompt: str) -> LLMResponse:
        raise LLMError("ReadTimeout: simulated")


def _service(settings: Settings, llm: LLMProvider) -> AnalyzerService:
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=MockSource(),
        extractor=EvidenceExtractor(
            EvidenceRegistry(), ProfileRegistry(settings.profiles_config_path)
        ),
        prompt_builder=PromptBuilder(settings.prompt_template_path, settings.confidence_buckets),
        llm_provider=llm,
        precheck=NoOpPreCheck(),
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

    async def resolve_run_id(self, job_id, run_id=""):  # type: ignore[no-untyped-def]
        return run_id or f"RUN_{job_id}"

    async def fetch_job(self, job_id, run_id=""):  # type: ignore[no-untyped-def]
        raise RuntimeError("VisiumGo unreachable")


@pytest.mark.asyncio
async def test_source_failure_finishes_run_with_note(settings: Settings) -> None:
    service = AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=FailingSource(),
        extractor=EvidenceExtractor(
            EvidenceRegistry(), ProfileRegistry(settings.profiles_config_path)
        ),
        prompt_builder=PromptBuilder(settings.prompt_template_path, settings.confidence_buckets),
        llm_provider=GarbageLLMProvider(),
        precheck=NoOpPreCheck(),
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
