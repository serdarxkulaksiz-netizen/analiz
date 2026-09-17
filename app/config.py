"""Single configuration layer — no hardcoded values."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    database_dir: Path = Path("database")
    table_runs: str = "runs"
    table_analysis_results: str = "analysis_results"
    table_evidence: str = "evidence"
    table_prompts: str = "prompts"
    table_llm_responses: str = "llm_responses"

    source_provider: str = "visiumgo"

    visiumgo_base_url: str = ""
    visiumgo_token: str = ""
    visiumgo_timeout_seconds: float = 60.0
    visiumgo_verify_ssl: bool = False
    visiumgo_build_log_entry: str = "build.log"

    profiles_config_path: Path = Path("config") / "profiles.json"

    precheck_provider: str = "noop"
    precheck_rules_path: Path = Path("config") / "precheck_rules.json"

    prompts_dir: Path = Path("config") / "prompts"
    confidence_buckets: list[float] = [0.1, 0.25, 0.5, 0.75, 0.99]

    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_endpoint_path: str = "/api/v1/extension/send"
    llm_api_key: str = ""
    llm_model: str = "qwen3-coder-next"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 8000
    llm_verify_ssl: bool = False

    max_concurrency: int = Field(default=2, ge=1)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    try:
        return Settings()
    except ValidationError as exc:
        unknown = [
            str(error["loc"][0])
            for error in exc.errors()
            if error["type"] == "extra_forbidden" and error["loc"]
        ]
        if not unknown:
            raise
        names = ", ".join(sorted(k.upper() for k in unknown))
        raise ValueError(
            f".env dosyasında tanınmayan ayar(lar): {names}. "
            "Yazım hatası olabilir, ya da anahtar kaldırılmış olabilir "
            "(ör. VISIUMGO_BUILD_LOG_PATH artık yok: /logs yolu kodda, çağrılıp "
            "çağrılmayacağına profil karar veriyor — satırı .env'den silin). "
            "Geçerli anahtarların tam listesi: .env.example"
        ) from None
