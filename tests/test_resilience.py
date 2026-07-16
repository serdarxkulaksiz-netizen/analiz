"""Error-resilience tests (plan.md A9): a bad LLM never kills the job."""

import pytest

from app.config import Settings
from app.llm.provider import LLMError, LLMProvider, LLMResponse
from app.main import build_service
from app.persistence.file_repository import FileRepository
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.mock import MockSource
from app.extraction.mock import MockExtractor


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
        extractor=MockExtractor(),
        prompt_builder=PromptBuilder(
            settings.prompt_template_path, settings.confidence_buckets
        ),
        llm_provider=llm,
    )


@pytest.mark.asyncio
async def test_garbage_llm_marks_scenarios_failed_but_job_finishes(
    settings: Settings,
) -> None:
    service = _service(settings, GarbageLLMProvider())
    run_id = service.create_run("demo", "job-1")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"
    assert run["completed_count"] == run["scenario_count"] == 2
    for result in run["results"]:
        assert result["analysis_failed"] is True
        assert result["verdict"] is None
        assert "ÜZGÜNÜM" in result["raw_llm_response"]  # raw answer kept
        assert result["explanation"] == ""  # no fabricated default text
        assert result["scenario_name"]  # identity still traceable


@pytest.mark.asyncio
async def test_llm_timeout_marks_scenarios_failed_but_job_finishes(
    settings: Settings,
) -> None:
    service = _service(settings, TimeoutLLMProvider())
    run_id = service.create_run("demo", "job-1")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"
    for result in run["results"]:
        assert result["analysis_failed"] is True
        assert "ReadTimeout" in result["raw_llm_response"]


@pytest.mark.asyncio
async def test_source_failure_finishes_run_with_note(settings: Settings) -> None:
    settings = settings.model_copy(update={"source_provider": "visiumgo"})
    service = build_service(settings)  # VisiumGoSource stub raises
    run_id = service.create_run("demo", "job-1")

    await service.run_analysis(run_id)

    run = service.get_run(run_id)
    assert run is not None
    assert run["status"] == "failed"
    assert "job failed" in run["note"]
