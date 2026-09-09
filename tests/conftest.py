"""Shared test fixtures — isolated settings per test (tmp database dir)."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.evidence.profiles import DEFAULT_PROFILE_NAME, JOB_FAILED_PROFILE_NAME, ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Mock-everything settings writing to a temporary database dir."""
    return Settings(
        _env_file=None,
        database_dir=tmp_path / "database",
        source_provider="mock",
        llm_provider="mock",
        precheck_provider="noop",
        prompts_dir=PROJECT_ROOT / "config" / "prompts",
        profiles_config_path=PROJECT_ROOT / "config" / "profiles.json",
        max_concurrency=2,
    )


@pytest.fixture
def profile_registry(settings: Settings) -> ProfileRegistry:
    return ProfileRegistry(settings.profiles_config_path)


@pytest.fixture
def extractor(profile_registry: ProfileRegistry) -> EvidenceExtractor:
    return EvidenceExtractor(EvidenceRegistry(), profile_registry)


def write_profiles(path: Path, profiles: dict, *, complete: bool = False) -> Path:
    """Write a profiles config, filling in what every legal config must carry.

    Two pieces of boilerplate a test about something else should not repeat:
    the mandatory `default_web` + `job_failed` profiles, and the rule that
    prompted evidence must also be stored (what is not downloaded cannot be
    prompted). `complete=True` writes the dict verbatim — that is how the
    fail-fast guards themselves are tested.
    """
    if complete:
        path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
        return path

    data = {DEFAULT_PROFILE_NAME: {}, JOB_FAILED_PROFILE_NAME: {}, **profiles}
    for row in data.values():
        if isinstance(row, dict) and "evidence_to_store" not in row:
            row["evidence_to_store"] = list(row.get("evidence_to_llm", []))
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path
