"""Shared test fixtures — isolated settings per test (tmp database dir)."""

from pathlib import Path

import pytest

from app.config import Settings
from app.evidence.profiles import ProfileRegistry
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
        prompt_template_path=PROJECT_ROOT / "config" / "prompt_template.txt",
        profiles_config_path=PROJECT_ROOT / "config" / "profiles.json",
        max_concurrency=2,
        cache_enabled=True,
    )


@pytest.fixture
def profile_registry(settings: Settings) -> ProfileRegistry:
    return ProfileRegistry(settings.profiles_config_path)


@pytest.fixture
def extractor(profile_registry: ProfileRegistry) -> EvidenceExtractor:
    return EvidenceExtractor(EvidenceRegistry(), profile_registry)
