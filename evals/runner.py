"""Golden-set runner: does a prompt change make the answers better or worse?

This is a **development tool**, not part of the service: nothing in `app/`
imports it. It replays hand-labelled scenarios through the real chain
(extraction -> profile -> prompt template -> LLM -> parsing) and compares the
model's `verdict` with the one a human wrote down.

Why it exists: after the prompt/profile changes nobody could say whether the
diagnoses got better or worse — the answer was a feeling. One command now turns
it into a number, and the report names the prompt version that produced it.

Usage (work PC, with the real `.env` so the real LLM answers):

    python -m evals.runner              # every case in evals/cases/*.json
    python -m evals.runner --strict     # exit code 1 if any case mismatches

A case file (`evals/cases/<ad>.json`):

    {
      "name": "login-locator-degismis",
      "expected_verdict": "test_maintenance",
      "job_id": "1321",
      "build_log": "",
      "scenario": {
        "scenario_name": "Login - geçerli kullanıcı",
        "error_text": "NoSuchElementException: #login-submit",
        "steps": [{"name": "Giriş butonuna tıkla", "status": "FAILED"}],
        "attachments": [
          {"file_name": "test.log", "mime_type": "text/plain",
           "device_id": "test", "content": "..."}
        ]
        # An attachment is identified by `device_id` + the file extension,
        # exactly like in production (`test.log` vs `test.properties`).
      }
    }

The set starts EMPTY on purpose: a golden set is only worth what the human
labels in it, and invented cases would measure nothing.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.llm.provider import LLMProvider
from app.main import LLM_REGISTRY
from app.parsing.json_parser import try_json
from app.prompting.builder import PromptBuilder
from app.source.models import RawScenario

CASES_DIR = Path(__file__).resolve().parent / "cases"


class EvalCase(BaseModel):
    """One hand-labelled scenario: the input, and the verdict a human expects."""

    name: str
    expected_verdict: str
    scenario: RawScenario
    job_id: str = ""
    build_log: str = ""


class EvalOutcome(BaseModel):
    """What the chain actually answered for one case."""

    name: str
    expected_verdict: str
    actual_verdict: str = ""
    ok: bool = False
    prompt_template: str = ""
    prompt_version: str = ""
    prompt_chars: int = 0
    note: str = ""


def load_cases(cases_dir: Path = CASES_DIR) -> list[EvalCase]:
    """Read every `*.json` case, newest naming order first (stable = sorted)."""
    return [
        EvalCase.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cases_dir.glob("*.json"))
    ]


async def run_case(
    case: EvalCase,
    extractor: EvidenceExtractor,
    builder: PromptBuilder,
    llm: LLMProvider,
) -> EvalOutcome:
    """Replay one case through the real chain and score its verdict."""
    findings = extractor.extract(
        case.scenario,
        job_id=case.job_id,
        build_log=case.build_log,
    )
    outcome = EvalOutcome(
        name=case.name,
        expected_verdict=case.expected_verdict,
        prompt_template=findings.prompt_template,
        prompt_version=builder.version_of(findings.prompt_template),
    )
    if not findings.has_evidence_for_llm:
        # Same rule as production: an empty prompt is not asked (app/service.py).
        outcome.note = "kanıt yok — LLM çağrılmadı"
        return outcome

    prompt = builder.build(findings)
    outcome.prompt_chars = len(prompt)
    try:
        response = await llm.complete(prompt)
    except Exception as exc:  # one bad case must not stop the run
        outcome.note = f"{type(exc).__name__}: {exc}"
        return outcome

    parsed = try_json(response.content)
    if not isinstance(parsed, dict):
        outcome.note = "cevap JSON değil"
        return outcome

    outcome.actual_verdict = str(parsed.get("verdict", ""))
    outcome.ok = outcome.actual_verdict == case.expected_verdict
    return outcome


async def run_all(cases: list[EvalCase], settings: Settings) -> list[EvalOutcome]:
    """Run every case against the providers the current `.env` selects."""
    extractor = EvidenceExtractor(
        EvidenceRegistry(), ProfileRegistry(settings.profiles_config_path)
    )
    builder = PromptBuilder(settings.prompts_dir, settings.confidence_buckets)
    llm = LLM_REGISTRY[settings.llm_provider](settings)
    return [await run_case(case, extractor, builder, llm) for case in cases]


def format_report(outcomes: list[EvalOutcome]) -> str:
    """Human-readable score table."""
    if not outcomes:
        return (
            f"Vaka yok. Elle etiketlenmiş senaryoları {CASES_DIR}/ altına *.json olarak "
            "koyun (biçim: evals/runner.py başındaki örnek)."
        )
    lines = [f"{'vaka':<34} {'beklenen':<18} {'gelen':<18} sonuç"]
    for row in outcomes:
        mark = "OK " if row.ok else "FARK"
        detail = row.actual_verdict or f"({row.note})"
        lines.append(f"{row.name:<34} {row.expected_verdict:<18} {detail:<18} {mark}")
    correct = sum(1 for row in outcomes if row.ok)
    versions = sorted(
        {f"{r.prompt_template}@{r.prompt_version}" for r in outcomes if r.prompt_version}
    )
    lines.append("")
    lines.append(f"skor: {correct}/{len(outcomes)} doğru   prompt: {', '.join(versions) or '-'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden-set prompt quality run")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="herhangi bir vaka tutmazsa çıkış kodu 1 olsun (CI için)",
    )
    parser.add_argument("--cases", type=Path, default=CASES_DIR, help="vaka klasörü")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    outcomes = asyncio.run(run_all(cases, get_settings()))
    print(format_report(outcomes))
    if args.strict and any(not row.ok for row in outcomes):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
