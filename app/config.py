"""Single configuration layer — no hardcoded values).

Every tunable — table names, URLs, model name, concurrency, confidence
buckets, profile/prompt file locations — lives here and is overridable via
environment variables / `.env` (see
`.env.example`). Defaults below mirror `.env.example`; only architecture-frozen
constants (enum values, block labels) live in code instead.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # A key in `.env` that no setting owns is an ERROR, not something to
        # skip quietly: a typo or a renamed key would otherwise leave the
        # feature silently off (e.g. the old VISIUMGO_JENKINS_LOG_PATH after
        # the build-log rename -> no build log, no warning, nobody notices).
        # Unrelated OS environment variables are unaffected; only the `.env`
        # file's own keys are checked.
        extra="forbid",
    )

    # --- persistence / DB simulation ---
    database_dir: Path = Path("database")
    table_runs: str = "runs"
    table_analysis_results: str = "analysis_results"
    table_evidence: str = "evidence"
    table_prompts: str = "prompts"
    table_llm_responses: str = "llm_responses"  # raw LLM answer per scenario

    # --- source / Halka 1 — value = registry key ---
    source_provider: str = "mock"  # mock | visiumgo

    # --- VisiumGo connection ; real source) — from.env, never code ---
    visiumgo_base_url: str = ""  # e.g. https://visiumgo.fintek.local
    visiumgo_token: str = ""  # JWT (eyJ...); code only puts it in the Bearer header
    visiumgo_timeout_seconds: float = 60.0
    # SSL verification off (internal self-signed certs); true to enable via .env.
    visiumgo_verify_ssl: bool = False
    # The `/logs` endpoint's PATH is not a setting — it is VisiumGo's own
    # contract and lives in `app/source/visiumgo.py`. Whether it is called at
    # all is a PROFILE decision (`BuildLogEvidence`). It used to be this
    # setting, which meant an unset key silently disabled the whole step and
    # recorded no reason for it.
    # Which file to read from inside that ZIP (matched on the entry's ending,
    # so `logs/build.log` matches too). This one IS a choice, so it stays.
    visiumgo_build_log_entry: str = "build.log"

    # --- extraction / Halka 2 ---
    # Analysis profiles: job_id -> which evidence goes to the
    # LLM / to the store, plus the content rules that trim each one.
    # New job behaviour = a row in this file, not code.
    profiles_config_path: Path = Path("config") / "profiles.json"

    # --- precheck / Halka before-prompt — value = registry key ---
    # noop = always go to the LLM (default). rules = answer known failures from
    # `precheck_rules_path` without calling the LLM.
    precheck_provider: str = "noop"  # noop | rules
    precheck_rules_path: Path = Path("config") / "precheck_rules.json"

    # --- prompt / Halka 3 ---
    # One template per job group (profile picks it by name) + the shared
    # `_contract.txt` that every template ends with.
    prompts_dir: Path = Path("config") / "prompts"
    confidence_buckets: list[float] = [0.1, 0.25, 0.5, 0.75, 0.99]

    # --- LLM / Halka 4 — value = registry key ---
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

    # --- API & background processing ---
    max_concurrency: int = 2  # asyncio.Semaphore size


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    A `.env` key that matches no setting fails here, at startup, with a message
    naming the key — instead of the feature silently staying off.
    """
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
