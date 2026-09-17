"""FastAPI app — async start/poll API."""

from collections.abc import Callable, Mapping
from typing import TypeVar

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

from app.config import Settings, get_settings
from app.domain.api import RunView, build_run_view
from app.domain.enums import RunStatus
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry, known_evidence_names
from app.extraction.evidence_extractor import EvidenceExtractor
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
from app.source.visiumgo import VisiumGoSource
from app.source.visiumgo_client import VisiumGoClient


class AnalyzeRequest(BaseModel):
    """Body of POST /analyze/visiumgo."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    parameter1: str = ""
    parameter2: str = ""
    job_id: str = ""
    run_id: str = ""

    @model_validator(mode="after")
    def _require_job_or_run(self) -> "AnalyzeRequest":
        if not self.job_id and not self.run_id:
            raise ValueError("Either job_id or run_id is required.")
        return self


def _attachments_dir(settings: Settings):
    return settings.database_dir / "attachments"


def _build_logs_dir(settings: Settings):
    """Where the job-level build log is written — one file per run."""
    return settings.database_dir / "build_logs"


SOURCE_REGISTRY: dict[str, Callable[[Settings], Source]] = {
    "visiumgo": lambda s: VisiumGoSource(
        VisiumGoClient(
            s.visiumgo_base_url,
            s.visiumgo_token,
            s.visiumgo_timeout_seconds,
            verify_ssl=s.visiumgo_verify_ssl,
        ),
        _attachments_dir(s),
        _build_logs_dir(s),
        build_log_entry=s.visiumgo_build_log_entry,
    ),
}

LLM_REGISTRY: dict[str, Callable[[Settings], LLMProvider]] = {
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


T = TypeVar("T")


def _select(
    registry: Mapping[str, Callable[[Settings], T]], key: str, kind: str
) -> Callable[[Settings], T]:
    """Look a factory up in a registry, or fail with a clear error."""
    try:
        return registry[key]
    except KeyError:
        known = ", ".join(sorted(registry)) or "<none>"
        raise ValueError(f"Unknown {kind} provider {key!r}. Known: {known}") from None


def build_service(settings: Settings) -> AnalyzerService:
    """Wire the whole chain from config (dependency injection root)."""
    profiles = ProfileRegistry(settings.profiles_config_path)
    prompt_builder = PromptBuilder(settings.prompts_dir, settings.confidence_buckets)
    prompt_builder.ensure_templates_exist(profiles.prompt_names())
    unknown = sorted(profiles.evidence_names() - known_evidence_names())
    if unknown:
        known = ", ".join(sorted(known_evidence_names()))
        raise ValueError(
            f"Profile(s) ask for unknown evidence: {', '.join(unknown)}. Known: {known}."
        )

    return AnalyzerService(
        settings=settings,
        repository=FileRepository(settings.database_dir),
        source=_select(SOURCE_REGISTRY, settings.source_provider, "source")(settings),
        extractor=EvidenceExtractor(EvidenceRegistry()),
        prompt_builder=prompt_builder,
        llm_provider=_select(LLM_REGISTRY, settings.llm_provider, "llm")(settings),
        precheck=_select(PRECHECK_REGISTRY, settings.precheck_provider, "precheck")(settings),
        profiles=profiles,
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
        background_tasks.add_task(service.run_analysis, analyzer_run_id)
        return {
            "analyzer_run_id": analyzer_run_id,
            "status": RunStatus.PENDING.value,
        }

    @app.get("/analyze/visiumgo/{analyzer_run_id}", response_model=RunView)
    async def get_analysis(analyzer_run_id: str) -> RunView:
        run = service.get_run(analyzer_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="analyzer_run_id not found")
        return build_run_view(run)

    return app


def __getattr__(name: str) -> FastAPI:
    """Build the ASGI app only when something actually asks for it (PEP 562)."""
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
