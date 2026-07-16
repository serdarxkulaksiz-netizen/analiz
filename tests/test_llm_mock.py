"""Mock LLM provider tests: schema-valid, contract-conforming output."""

import pytest

from app.domain.result import LLMAnalysis
from app.llm.mock import MockLLMProvider
from app.parsing.json_parser import _try_json


@pytest.mark.asyncio
async def test_mock_returns_schema_valid_json() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete(
        "Platform: web\nSenaryo: Login testi\n... NoSuchElementException ..."
    )

    parsed = _try_json(response.content)
    assert parsed is not None
    analysis = LLMAnalysis.model_validate(parsed)
    assert analysis.scenario_name == "Login testi"
    assert analysis.platform == "web"
    assert analysis.verdict.value == "test_maintenance"
    assert response.model == "mock-model"


@pytest.mark.asyncio
async def test_mock_maps_auth_evidence_to_environment_error() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete(
        "Platform: web\nSenaryo: Hesap özeti\n... 401 Unauthorized ..."
    )

    parsed = _try_json(response.content)
    assert parsed is not None
    analysis = LLMAnalysis.model_validate(parsed)
    assert analysis.verdict.value == "environment_error"


@pytest.mark.asyncio
async def test_mock_confidence_is_a_known_bucket() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete("Platform: web\nSenaryo: X")

    parsed = _try_json(response.content)
    assert parsed is not None
    assert parsed["confidence"] in {0.1, 0.25, 0.5, 0.75, 0.99}
