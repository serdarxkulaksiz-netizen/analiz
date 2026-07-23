"""Mock LLM provider — deterministic, schema-valid answer for local development.

Lets the whole chain run end-to-end without a real LLM (plan.md A15). Returns
ONE fixed, contract-valid diagnosis — no content-based branching (plan.md A0.1).

`MOCK_` labeling (plan.md A14.2): every free-text field the mock fabricates
starts with `MOCK_`, so mock data never blends with real data in `database/`.
Two fields are intentionally NOT prefixed: `verdict` (enum) and `confidence`
(float) must stay valid values; and `scenario_name` is echoed from the prompt
(the mock source already prefixes real scenario names with `MOCK_`), which keeps
the trace rows aligned across evidence/prompts/analysis_results.
"""

import json
import time

from app.llm.provider import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Returns a fixed, contract-valid JSON diagnosis (free text in Turkish)."""

    def __init__(self, model: str, confidence: float = 0.75) -> None:
        self._model = model
        self._confidence = confidence

    @staticmethod
    def _echo_scenario_name(prompt: str) -> str:
        for line in prompt.splitlines():
            if line.startswith("Senaryo:"):
                return line[len("Senaryo:") :].strip()
        return "MOCK_bilinmeyen senaryo"

    async def complete(self, prompt: str) -> LLMResponse:
        started = time.perf_counter()
        payload = {
            "scenario_name": self._echo_scenario_name(prompt),
            "root_cause": "MOCK_örnek kök neden: bu sahte bir teşhistir, gerçek LLM bağlanınca değişecek.",
            "error_type": "MOCK_ExampleError",
            "verdict": "test_maintenance",
            "explanation": "MOCK_ bu sahte bir açıklamadır; kanıta dayalı gerçek yorum yerine sabit örnek.",
            "suggestion": "MOCK_ örnek öneri: gerçek LLM sağlayıcısını .env üzerinden etkinleştirin.",
            "confidence": self._confidence,
            "confidence_reason": "MOCK_ sabit örnek güven gerekçesi (sahte).",
            "summary": "MOCK_ bu sahte bir teşhis özetidir.",
            "most_relevant_log_lines": ["MOCK_ örnek en ilgili log satırı"],
            "error_signature": "MOCK_example-signature",
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=len(prompt) // 4,
            output_tokens=len(content) // 4,
            duration_ms=duration_ms,
        )
