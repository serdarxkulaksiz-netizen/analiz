"""Single configuration layer (plan.md A0.2 — no hardcoded values).

Every tunable — table names, URLs, model name, truncation threshold,
concurrency, confidence buckets, evidence flags, prompt template location —
lives here and is overridable via environment variables / `.env` (see
`.env.example`). Defaults below mirror `.env.example`; only architecture-frozen
constants (enum values, block labels) live in code instead.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Evidence flag defaults (plan.md A5.2): per evidence type, does it go to the
# LLM and/or the store. Keys are the evidence class names (registry keys).
# Screenshots are stored but not sent to the (text) LLM today.
_DEFAULT_EVIDENCE_FLAGS: dict[str, dict[str, bool]] = {
    "TestLogEvidence": {"goes_to_llm": True, "goes_to_store": True},
    "HtmlEvidence": {"goes_to_llm": True, "goes_to_store": True},
    "BrowserLogEvidence": {"goes_to_llm": True, "goes_to_store": True},
    "WebScreenshotEvidence": {"goes_to_llm": False, "goes_to_store": True},
    "MobileScreenshotEvidence": {"goes_to_llm": False, "goes_to_store": True},
}


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

    # --- source / Halka 1 (plan.md A4) — value = registry key ---
    source_provider: str = "mock"  # mock | visiumgo
    banks_config_path: Path = Path("config") / "banks.json"

    # --- extraction & size management / Halka 2 (plan.md A5, A11) ---
    extractor_provider: str = "mock"  # mock | visiumgo
    truncation_threshold_tokens: int = 0  # 0 = passthrough (default)
    token_chars_ratio: int = 4  # rough chars-per-token estimate
    # Per-evidence-type flags (A5.2): goes_to_llm / goes_to_store.
    evidence_flags: dict[str, dict[str, bool]] = Field(
        default_factory=lambda: _DEFAULT_EVIDENCE_FLAGS
    )

    # --- precheck / Halka before-prompt (plan.md A7) — value = registry key ---
    precheck_provider: str = "noop"  # noop (only implementation today)

    # --- prompt / Halka 3 (plan.md A8) ---
    prompt_template_path: Path = Path("config") / "prompt_template.txt"
    confidence_buckets: list[float] = [0.1, 0.25, 0.5, 0.75, 0.99]

    # --- LLM / Halka 4 (plan.md A9) — value = registry key ---
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
