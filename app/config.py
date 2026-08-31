"""Single configuration layer (plan.md A0.2 — no hardcoded values).

Every tunable — table names, URLs, model name, concurrency, confidence
buckets, profile/prompt file locations — lives here and is overridable via
environment variables / `.env` (see
`.env.example`). Defaults below mirror `.env.example`; only architecture-frozen
constants (enum values, block labels) live in code instead.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- persistence / DB simulation (plan.md A12) ---
    database_dir: Path = Path("database")
    table_runs: str = "runs"
    table_analysis_results: str = "analysis_results"
    table_evidence: str = "evidence"
    table_prompts: str = "prompts"
    table_llm_responses: str = "llm_responses"  # raw LLM answer per scenario

    # --- source / Halka 1 (plan.md A4) — value = registry key ---
    source_provider: str = "mock"  # mock | visiumgo

    # --- VisiumGo connection (plan.md A4; real source) — from .env, never code ---
    visiumgo_base_url: str = ""  # e.g. https://visiumgo.fintek.local
    visiumgo_token: str = ""  # JWT (eyJ...); code only puts it in the Bearer header
    visiumgo_timeout_seconds: float = 60.0
    # SSL verification off (internal self-signed certs); true to enable via .env.
    visiumgo_verify_ssl: bool = False
    # VisiumGo endpoint serving the job's Jenkins console log; `{run_id}` is
    # substituted. Empty = skip (the endpoint is being added on the VisiumGo
    # side; nothing breaks until it exists).
    visiumgo_jenkins_log_path: str = ""

    # --- extraction / Halka 2 (plan.md A5) ---
    # Analysis profiles: job_id (or parameter1) -> which evidence goes to the
    # LLM / to the store, plus the content rules that trim each one.
    # New job behaviour = a row in this file, not code.
    profiles_config_path: Path = Path("config") / "profiles.json"

    # --- precheck / Halka before-prompt (plan.md A7) — value = registry key ---
    precheck_provider: str = "noop"  # noop (only implementation today)

    # --- prompt / Halka 3 (plan.md A8) ---
    prompt_template_path: Path = Path("config") / "prompt_template.txt"
    confidence_buckets: list[float] = [0.1, 0.25, 0.5, 0.75, 0.99]

    # --- LLM / Halka 4 (plan.md A9) — value = registry key ---
    llm_provider: str = "mock"  # mock | openai_compatible
    # Base URL + path are separate so switching to a direct LLM server later is
    # a single config change (no code). Full URL = base_url + endpoint_path.
    llm_base_url: str = ""  # e.g. https://test-automation-ai-api.apps.nonfin-vip.zke.zb
    llm_endpoint_path: str = "/api/v1/extension/send"
    llm_api_key: str = ""  # no auth for this service; header sent only if set
    llm_model: str = "qwen3-coder-next"  # meta only; NOT sent in the request body
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 8000
    # SSL verification off (internal self-signed certs); true to enable via .env.
    llm_verify_ssl: bool = False

    # --- API & background processing (plan.md A11) ---
    max_concurrency: int = 2  # asyncio.Semaphore size
    # Run cache off: the same job is always re-analyzed (no reuse of prior runs).
    cache_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
