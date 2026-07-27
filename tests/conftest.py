"""Shared test fixtures — isolated settings per test (tmp database dir)."""

from pathlib import Path

import pytest

from app.config import Settings
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
        max_concurrency=2,
        cache_enabled=True,
    )


@pytest.fixture
def evidence_registry(settings: Settings) -> EvidenceRegistry:
    """Registry wired with the settings' evidence flags."""
    return EvidenceRegistry(settings.evidence_flags)


@pytest.fixture
def extractor(evidence_registry: EvidenceRegistry) -> EvidenceExtractor:
    return EvidenceExtractor(evidence_registry)
