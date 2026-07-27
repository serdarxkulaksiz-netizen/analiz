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

    # --- VisiumGo connection (plan.md A4; real source) — from .env, never code ---
    visiumgo_base_url: str = ""  # e.g. https://visiumgo.fintek.local
    visiumgo_token: str = ""  # JWT (eyJ...); code only puts it in the Bearer header
    visiumgo_timeout_seconds: float = 60.0
    # SSL verification off (internal self-signed certs); true to enable via .env.
    visiumgo_verify_ssl: bool = False

    # --- extraction & size management / Halka 2 (plan.md A5, A11) ---
    # Reserved for later (plan.md A11): the single "when to trim" threshold.
    # Not wired yet — today everything is passthrough; real Evidence-level
    # trimming + real token counting land on the work PC. 0 = passthrough.
    truncation_threshold_tokens: int = 0
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
