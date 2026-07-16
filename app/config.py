"""Single configuration layer (plan.md A0.1 — no hardcoded values).

Every tunable — table names, URLs, model name, truncation threshold,
concurrency, confidence buckets, prompt template location — lives here and is
overridable via environment variables / `.env` (see `.env.example`).
Defaults below mirror `.env.example`; only architecture-frozen constants
(enum values, block labels) live in code instead.
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

    # --- persistence / DB simulation (plan.md A10) ---
    database_dir: Path = Path("database")
    table_runs: str = "runs"
    table_analysis_results: str = "analysis_results"
    table_evidence: str = "evidence"
    table_prompts: str = "prompts"

    # --- source / Halka 1 (plan.md A4) ---
    source_provider: str = "mock"  # mock | visiumgo
    banks_config_path: Path = Path("config") / "banks.json"

    # --- extraction & size management / Halka 2 (plan.md A5) ---
    extractor_provider: str = "mock"  # mock | visiumgo
    truncation_threshold_tokens: int = 0  # 0 = passthrough (default)
    token_chars_ratio: int = 4  # rough chars-per-token estimate

    # --- prompt / Halka 3 (plan.md A7) ---
    prompt_template_path: Path = Path("config") / "prompt_template.txt"
    confidence_buckets: list[float] = [0.1, 0.25, 0.5, 0.75, 0.99]

    # --- LLM / Halka 4 (plan.md A9) ---
    llm_provider: str = "mock"  # mock | openai_compatible
    llm_api_url: str = ""  # full OpenAI-compatible chat-completions URL
    llm_api_key: str = ""
    llm_model: str = "mock-model"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int | None = None

    # --- API & background processing (plan.md A11) ---
    max_concurrency: int = 2  # asyncio.Semaphore size
    cache_enabled: bool = True  # reuse previous analysis of same bank+job_id


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
