"""FastAPI app — async start/poll API (plan.md A13).

Endpoints (names frozen, plan.md B3.2):
  POST /analyze/visiumgo {parameter1?, parameter2?, job_id?/run_id?} -> analyzer_run_id
  GET  /analyze/visiumgo/{analyzer_run_id} -> status + finished diagnoses (from disk)

Every pluggable backend (source, LLM, precheck) is chosen from config via a
REGISTRY (name -> factory) and injected here — no `if provider ==` branching
(plan.md A0.1). Extraction is a single source-agnostic implementation. Switching
mock -> real VisiumGo is a `.env` change, not code.
"""

from collections.abc import Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, model_validator

from app.config import Settings, get_settings
from app.domain.enums import RunStatus
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.llm.provider import LLMProvider
from app.persistence.file_repository import FileRepository
from app.precheck.base import PreCheck
from app.precheck.noop import NoOpPreCheck
from app.precheck.rule_based import RuleBasedPreCheck
from app.precheck.rules import load_rules
from app.prompting.builder import PromptBuilder
from app.service import AnalyzerService
from app.source.base import Source
from app.source.mock import MockSource
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient


class AnalyzeRequest(BaseModel):
    """Body of POST /analyze/visiumgo.

    `parameter1`/`parameter2` are generic customization keys selecting the
    analysis profile (config/profiles.json); omitted -> "default". Either
    `job_id` or `run_id` must be given (run_id wins if both are present).
    """

    parameter1: str = "default"
    parameter2: str = "default"
    job_id: str = ""
    run_id: str = ""

    @model_validator(mode="after")
    def _require_job_or_run(self) -> "AnalyzeRequest":
        if not self.job_id and not self.run_id:
            raise ValueError("Either job_id or run_id is required.")
        return self


def _attachments_dir(settings: Settings):
    return settings.database_dir / "attachments"


# --- Registries (plan.md A0.1): name -> factory. A new variant = one row. -----

SOURCE_REGISTRY: dict[str, Callable[[Settings], Source]] = {
    "mock": lambda s: MockSource(),
    "visiumgo": lambda s: VisiumGoSource(
        VisiumGoClient(
            s.visiumgo_base_url,
            s.visiumgo_token,
            s.visiumgo_timeout_seconds,
            verify_ssl=s.visiumgo_verify_ssl,
        ),
        _attachments_dir(s),
        build_log_path=s.visiumgo_build_log_path,
        build_log_entry=s.visiumgo_build_log_entry,
    ),
}

LLM_REGISTRY: dict[str, Callable[[Settings], LLMProvider]] = {
    "mock": lambda s: MockLLMProvider(model=s.llm_model),
    "openai_compatible": lambda s: OpenAICompatibleLLMProvider(
        base_url=s.llm_base_url,
        endpoint_path=s.llm_endpoint_path,
        api_key=s.llm_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        timeout_seconds=s.llm_timeout_seconds,
        max_tokens=s.llm_max_tokens,
        verify_ssl=s.llm_verify_ssl,
    ),
}

PRECHECK_REGISTRY: dict[str, Callable[[Settings], PreCheck]] = {
    "noop": lambda s: NoOpPreCheck(),
    "rules": lambda s: RuleBasedPreCheck(load_rules(s.precheck_rules_path)),
}


def _select(registry: dict[str, Callable[[Settings], object]], key: str, kind: str):
    """Look a factory up in a registry, or fail with a clear error."""
    try:
        return registry[key]
    except KeyError:
        known = ", ".join(sorted(registry)) or "<none>"
        raise ValueError(f"Unknown {kind} provider {key!r}. Known: {known}") from None


def build_service(settings: Settings) -> AnalyzerService:
    """Wire the whole chain from config (dependency injection root)."""
    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=_select(SOURCE_REGISTRY, settings.source_provider, "source")(settings),
        extractor=EvidenceExtractor(
            EvidenceRegistry(), ProfileRegistry(settings.profiles_config_path)
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

    app = FastAPI(title="VisiumGo Test Analyzer", version="0.3.0")
    app.state.service = service

    @app.post("/analyze/visiumgo")
    async def start_analysis(
        request: AnalyzeRequest, background_tasks: BackgroundTasks
    ) -> dict[str, str]:
        analyzer_run_id = service.create_run(
            request.parameter1, request.job_id, request.parameter2, request.run_id
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
