"""FastAPI app — async start/poll API (plan.md A11).

Endpoints (names frozen, plan.md B3.2):
  POST /analyze/visiumgo {bank, job_id} -> returns analyzer_run_id immediately
  GET  /analyze/visiumgo/{analyzer_run_id} -> status + finished diagnoses (from disk)

All backends (source, extractor, LLM, repository) are chosen from config and
injected here — switching mock -> real is a `.env` change, not a code change.
"""

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.domain.enums import RunStatus
from app.extraction.base import Extractor
from app.extraction.mock import MockExtractor
from app.extraction.visiumgo import VisiumGoExtractor
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.llm.provider import LLMProvider
from app.persistence.file_repository import FileRepository
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.banks import BankRegistry
from app.source.base import Source
from app.source.mock import MockSource
from app.source.visiumgo import VisiumGoSource


class AnalyzeRequest(BaseModel):
    """Body of POST /analyze/visiumgo (plan.md A11)."""

    bank: str
    job_id: str


def _build_source(settings: Settings) -> Source:
    if settings.source_provider == "mock":
        return MockSource()
    if settings.source_provider == "visiumgo":
        return VisiumGoSource(BankRegistry(settings.banks_config_path))
    raise ValueError(f"Unknown SOURCE_PROVIDER: {settings.source_provider!r}")


def _build_extractor(settings: Settings) -> Extractor:
    if settings.extractor_provider == "mock":
        return MockExtractor()
    if settings.extractor_provider == "visiumgo":
        return VisiumGoExtractor()
    raise ValueError(f"Unknown EXTRACTOR_PROVIDER: {settings.extractor_provider!r}")


def _build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider(model=settings.llm_model)
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            api_url=settings.llm_api_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")


def build_service(settings: Settings) -> AnalyzerService:
    """Wire the whole chain from config (dependency injection root)."""
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=_build_source(settings),
        extractor=_build_extractor(settings),
        prompt_builder=PromptBuilder(
            settings.prompt_template_path, settings.confidence_buckets
        ),
        llm_provider=_build_llm_provider(settings),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory (also used by tests with isolated settings)."""
    settings = settings or get_settings()
    service = build_service(settings)

    app = FastAPI(title="VisiumGo Test Analyzer", version="0.1.0")
    app.state.service = service

    @app.post("/analyze/visiumgo")
    async def start_analysis(
        request: AnalyzeRequest, background_tasks: BackgroundTasks
    ) -> dict[str, str]:
        analyzer_run_id = service.create_run(request.bank, request.job_id)
        # Single trigger call — swapping BackgroundTasks for a real queue
        # (Redis) only changes this line (plan.md A11).
        background_tasks.add_task(service.run_analysis, analyzer_run_id)
        return {
            "analyzer_run_id": analyzer_run_id,
            "status": RunStatus.PENDING.value,
        }

    @app.get("/analyze/visiumgo/{analyzer_run_id}")
    async def get_analysis(analyzer_run_id: str) -> dict:
        run = service.get_run(analyzer_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="analyzer_run_id not found")
        return run

    return app


app = create_app()
