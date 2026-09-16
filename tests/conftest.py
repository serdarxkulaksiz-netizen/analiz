"""Shared test fixtures — isolated settings per test (tmp database dir)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.domain.findings import Findings
from app.evidence.profiles import DEFAULT_PROFILE_NAME, JOB_FAILED_PROFILE_NAME, ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.source.models import RawScenario

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Real providers, temporary database dir, no `.env` on the machine read.

    Nothing here reaches the network: the tests that touch a provider inject a
    fake httpx transport into it, so the real client code runs against a fake
    wire instead of a fake client.
    """
    return Settings(
        _env_file=None,
        database_dir=tmp_path / "database",
        source_provider="visiumgo",
        llm_provider="openai_compatible",
        precheck_provider="noop",
        # Addresses that exist only so the real clients can be constructed.
        # Nothing contacts them: a test that needs an answer injects a fake
        # httpx transport, and the rest never issues a request at all.
        visiumgo_base_url="https://visiumgo.test.local",
        visiumgo_token="eyJtest",
        llm_base_url="https://llm.test.local",
        prompts_dir=PROJECT_ROOT / "config" / "prompts",
        profiles_config_path=PROJECT_ROOT / "config" / "profiles.json",
        max_concurrency=2,
    )


@pytest.fixture
def profile_registry(settings: Settings) -> ProfileRegistry:
    return ProfileRegistry(settings.profiles_config_path)


@pytest.fixture
def extract(profile_registry: ProfileRegistry) -> Callable[..., Findings]:
    """Extract with the profile a job_id resolves to — what the service does.

    The extractor no longer looks profiles up; the run resolves one and hands
    the object down. This binds the two steps the way `_run_job` binds them.
    """
    extractor = EvidenceExtractor(EvidenceRegistry())

    def run(
        scenario: RawScenario, *, job_id: str = "", forced: str = "", **kwargs: Any
    ) -> Findings:
        profile = profile_registry.get(job_id=job_id, forced=forced)
        return extractor.extract(scenario, profile=profile, **kwargs)

    return run


def write_profiles(path: Path, profiles: dict, *, complete: bool = False) -> Path:
    """Write a profiles config, filling in what every legal config must carry.

    Three pieces of boilerplate a test about something else should not repeat:
    the mandatory `default_web` + `job_failed` profiles, the rule that prompted
    evidence must also be stored (what is not downloaded cannot be prompted),
    and the prompt template every profile must now name (there is no fallback).
    `complete=True` writes the dict verbatim — that is how the fail-fast guards
    themselves are tested.
    """
    if complete:
        path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
        return path

    data = {DEFAULT_PROFILE_NAME: {}, JOB_FAILED_PROFILE_NAME: {}, **profiles}
    for row in data.values():
        if not isinstance(row, dict):
            continue
        if "evidence_to_store" not in row:
            row["evidence_to_store"] = list(row.get("evidence_to_llm", []))
        row.setdefault("prompt", "web")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path
