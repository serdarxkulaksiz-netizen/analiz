"""FastAPI app — async start/poll API (plan.md A13).

Endpoints (names frozen, plan.md B3.2):
  POST /analyze/visiumgo {bank, job_id, platform} -> analyzer_run_id (immediately)
  GET  /analyze/visiumgo/{analyzer_run_id} -> status + finished diagnoses (from disk)

Every pluggable backend (source, extractor, LLM, precheck) is chosen from
config via a REGISTRY (name -> factory) and injected here — no `if provider ==`
branching (plan.md A0.1). Switching mock -> real is a `.env` change, not code.
"""

from collections.abc import Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.domain.enums import Platform, RunStatus
from app.evidence.registry import EvidenceRegistry
from app.extraction.base import Extractor
from app.extraction.mock import MockExtractor
from app.extraction.visiumgo import VisiumGoExtractor
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.llm.provider import LLMProvider
from app.persistence.file_repository import FileRepository
from app.precheck.base import PreCheck
from app.precheck.noop import NoOpPreCheck
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.banks import BankRegistry
from app.source.base import Source
from app.source.mock import MockSource
from app.source.visiumgo import VisiumGoSource


class AnalyzeRequest(BaseModel):
    """Body of POST /analyze/visiumgo (plan.md A13). `platform` is input (A4.2)."""

    bank: str
    job_id: str
    platform: Platform


def _build_evidence_registry(settings: Settings) -> EvidenceRegistry:
    return EvidenceRegistry(settings.evidence_flags)


# --- Registries (plan.md A0.1): name -> factory. A new variant = one row. -----

SOURCE_REGISTRY: dict[str, Callable[[Settings], Source]] = {
    "mock": lambda s: MockSource(),
    "visiumgo": lambda s: VisiumGoSource(BankRegistry(s.banks_config_path)),
}

EXTRACTOR_REGISTRY: dict[str, Callable[[Settings], Extractor]] = {
    "mock": lambda s: MockExtractor(_build_evidence_registry(s)),
    "visiumgo": lambda s: VisiumGoExtractor(_build_evidence_registry(s)),
}

LLM_REGISTRY: dict[str, Callable[[Settings], LLMProvider]] = {
    "mock": lambda s: MockLLMProvider(model=s.llm_model),
    "openai_compatible": lambda s: OpenAICompatibleLLMProvider(
        api_url=s.llm_api_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        timeout_seconds=s.llm_timeout_seconds,
        max_tokens=s.llm_max_tokens,
    ),
}

PRECHECK_REGISTRY: dict[str, Callable[[Settings], PreCheck]] = {
    "noop": lambda s: NoOpPreCheck(),
}


def _select(registry: dict[str, Callable[[Settings], object]], key: str, kind: str):
    """Look a factory up in a registry and build it, or fail with a clear error."""
    try:
        factory = registry[key]
    except KeyError:
        known = ", ".join(sorted(registry)) or "<none>"
        raise ValueError(f"Unknown {kind} provider {key!r}. Known: {known}") from None
    return factory


def build_service(settings: Settings) -> AnalyzerService:
    """Wire the whole chain from config (dependency injection root)."""
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=_select(SOURCE_REGISTRY, settings.source_provider, "source")(settings),
        extractor=_select(EXTRACTOR_REGISTRY, settings.extractor_provider, "extractor")(
            settings
        ),
        prompt_builder=PromptBuilder(
            settings.prompt_template_path, settings.confidence_buckets
        ),
        llm_provider=_select(LLM_REGISTRY, settings.llm_provider, "llm")(settings),
        precheck=_select(PRECHECK_REGISTRY, settings.precheck_provider, "precheck")(
            settings
        ),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory (also used by tests with isolated settings)."""
    settings = settings or get_settings()
    service = build_service(settings)

    app = FastAPI(title="VisiumGo Test Analyzer", version="0.2.0")
    app.state.service = service

    @app.post("/analyze/visiumgo")
    async def start_analysis(
        request: AnalyzeRequest, background_tasks: BackgroundTasks
    ) -> dict[str, str]:
        analyzer_run_id = service.create_run(
            request.bank, request.job_id, request.platform
        )
        # Single trigger call — swapping BackgroundTasks for a real queue
        # (Redis) only changes this line (plan.md A13).
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
