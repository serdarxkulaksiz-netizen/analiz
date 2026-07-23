"""Mock LLM provider tests: single schema-valid, MOCK_-labeled diagnosis."""

import pytest

from app.domain.result import LLMAnalysis
from app.llm.mock import MockLLMProvider
from app.parsing.json_parser import _try_json


@pytest.mark.asyncio
async def test_mock_returns_schema_valid_json() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete(
        "Platform: web\nSenaryo: MOCK_Login testi\n... NoSuchElementException ..."
    )

    parsed = _try_json(response.content)
    assert parsed is not None
    analysis = LLMAnalysis.model_validate(parsed)
    # scenario_name is echoed from the prompt (keeps trace rows aligned).
    assert analysis.scenario_name == "MOCK_Login testi"
    assert analysis.verdict.value == "test_maintenance"
    assert response.model == "mock-model"


@pytest.mark.asyncio
async def test_mock_free_text_fields_are_prefixed() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete("Platform: web\nSenaryo: MOCK_X")

    parsed = _try_json(response.content)
    assert parsed is not None
    # Every fabricated free-text field starts with MOCK_ (plan.md A14.2).
    for field in (
        "root_cause",
        "error_type",
        "explanation",
        "suggestion",
        "confidence_reason",
        "summary",
        "error_signature",
    ):
        assert parsed[field].startswith("MOCK_"), field
    assert all(line.startswith("MOCK_") for line in parsed["most_relevant_log_lines"])


@pytest.mark.asyncio
async def test_mock_is_deterministic_regardless_of_content() -> None:
    # No content-based branching (plan.md A0.1): auth evidence changes nothing.
    provider = MockLLMProvider(model="mock-model")
    a = _try_json((await provider.complete("Senaryo: MOCK_A\n401 Unauthorized")).content)
    b = _try_json((await provider.complete("Senaryo: MOCK_A\nNoSuchElement")).content)
    assert a is not None and b is not None
    assert a["verdict"] == b["verdict"] == "test_maintenance"


@pytest.mark.asyncio
async def test_mock_confidence_is_a_known_bucket() -> None:
    provider = MockLLMProvider(model="mock-model")
    response = await provider.complete("Platform: web\nSenaryo: MOCK_X")

    parsed = _try_json(response.content)
    assert parsed is not None
    assert parsed["confidence"] in {0.1, 0.25, 0.5, 0.75, 0.99}
