"""Golden-set harness tests (development tool, not part of the service).

The harness exists to turn "the answers got worse" into a number. These tests
check the scoring itself with a stub LLM — the real model is only reachable
from the work network.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.llm.provider import LLMProvider, LLMResponse
from evals.runner import EvalCase, format_report, load_cases, run_all


class FixedVerdictLLM(LLMProvider):
    """Always answers with the same verdict, so scoring is deterministic."""

    def __init__(self, verdict: str) -> None:
        self._verdict = verdict

    async def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({"verdict": self._verdict, "confidence": 0.75}),
            model="fixed",
        )


def _case(name: str, expected: str) -> dict:
    return {
        "name": name,
        "expected_verdict": expected,
        "scenario": {
            "scenario_name": "Senaryo",
            "error_text": "NoSuchElementException: #btn",
            "steps": [{"name": "Adım", "status": "FAILED"}],
            "attachments": [
                {
                    "file_name": "test.log",
                    "mime_type": "text/plain",
                    "device_id": "test",
                    "content": "log satırı",
                }
            ],
        },
    }


def _write_cases(tmp_path: Path, cases: list[dict]) -> Path:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for case in cases:
        (cases_dir / f"{case['name']}.json").write_text(json.dumps(case), encoding="utf-8")
    return cases_dir


def test_empty_set_is_not_an_error(tmp_path: Path) -> None:
    """The set ships empty on purpose — invented cases would measure nothing."""
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()

    assert load_cases(cases_dir) == []
    assert "Vaka yok" in format_report([])


@pytest.mark.asyncio
async def test_score_counts_matching_verdicts(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        __import__("evals.runner", fromlist=["LLM_REGISTRY"]).LLM_REGISTRY,
        "mock",
        lambda s: FixedVerdictLLM("test_maintenance"),
    )
    cases_dir = _write_cases(
        tmp_path,
        [_case("tutan", "test_maintenance"), _case("tutmayan", "application_bug")],
    )

    outcomes = await run_all(load_cases(cases_dir), settings)
    report = format_report(outcomes)

    assert [row.ok for row in outcomes] == [True, False]  # sorted by file name
    assert "skor: 1/2 doğru" in report
    # The report names the prompt version behind the score — that is what makes
    # a later regression traceable to a prompt change.
    assert "prompt: web@" in report  # the fallback profile's template
    assert all(row.prompt_version for row in outcomes)


@pytest.mark.asyncio
async def test_case_without_evidence_is_not_sent_to_the_llm(
    settings: Settings, tmp_path: Path
) -> None:
    """Same rule as production: an empty prompt is never asked."""
    bare = {
        "name": "kanitsiz",
        "expected_verdict": "unknown",
        "scenario": {"scenario_name": "Boş senaryo"},
    }
    outcomes = await run_all(load_cases(_write_cases(tmp_path, [bare])), settings)

    assert outcomes[0].note == "kanıt yok — LLM çağrılmadı"
    assert outcomes[0].actual_verdict == ""


def test_case_model_accepts_the_documented_shape() -> None:
    """The example file in evals/cases must stay loadable as a case."""
    example = Path("evals/cases/ornek-vaka.json.example")
    case = EvalCase.model_validate_json(example.read_text(encoding="utf-8"))

    assert case.expected_verdict == "test_maintenance"
    assert case.scenario.attachments[0].device_id == "test"
