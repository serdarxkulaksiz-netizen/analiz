"""Mock LLM provider — deterministic, schema-valid answers for local development.

Lets the whole chain run end-to-end without a real LLM (plan.md A12). The
canned Turkish content below is mock *fixture data*, not product defaults.

The mock echoes scenario identity by scanning the prompt for the
`Senaryo:` / `Platform:` lines that `config/prompt_template.txt` renders —
a mock-only convenience, not a product parser.
"""

import json
import time

from app.llm.provider import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Returns a fixed, contract-valid JSON diagnosis (content in Turkish)."""

    def __init__(self, model: str, confidence: float = 0.75) -> None:
        self._model = model
        self._confidence = confidence

    @staticmethod
    def _find_line_value(prompt: str, prefix: str) -> str:
        for line in prompt.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return ""

    async def complete(self, prompt: str) -> LLMResponse:
        started = time.perf_counter()
        scenario_name = self._find_line_value(prompt, "Senaryo:")
        platform = self._find_line_value(prompt, "Platform:")

        # Cheap cue so mock runs produce varied verdicts: an auth failure in
        # the evidence reads as an environment problem, anything else as a
        # stale test. The full phrase is required because the template's own
        # rule text mentions the bare "401".
        if "401 Unauthorized" in prompt:
            payload = {
                "scenario_name": scenario_name,
                "platform": platform,
                "root_cause": "Servis 401 Unauthorized döndü; test ortamının yetkilendirmesi sorunlu görünüyor.",
                "error_type": "AuthenticationError",
                "verdict": "environment_error",
                "explanation": "Adımlar servise istek atıldığında 401 aldı; test de uygulama da suçsuz, ortam/yetki kaynaklı.",
                "suggestion": "Test ortamındaki servis kimlik bilgilerini/token'ı yenileyin ve koşuyu tekrarlayın.",
                "confidence": self._confidence,
                "confidence_reason": "401 kanıtı net; ancak token mı yoksa servis konfigürasyonu mu olduğu kanıttan ayırt edilemiyor.",
                "summary": "Ortam yetkilendirme hatası (401); testi güncellemeye gerek yok.",
                "most_relevant_log_lines": [
                    line for line in prompt.splitlines() if "401" in line
                ][:3],
                "error_signature": "http-401-unauthorized",
            }
        else:
            payload = {
                "scenario_name": scenario_name,
                "platform": platform,
                "root_cause": "Beklenen element DOM'da bulunamadı; selector eskimiş görünüyor.",
                "error_type": "NoSuchElementException",
                "verdict": "test_maintenance",
                "explanation": "Patlayan adım bir elemente erişmeye çalışırken element bulunamadı; DOM dökümünde elementin beklenen kimliği yok.",
                "suggestion": "Senaryodaki ilgili selector'ı güncel DOM'a göre güncelleyin.",
                "confidence": self._confidence,
                "confidence_reason": "Hata mesajı ile DOM dökümü tutarlı; ancak uygulamanın kasıtlı bir UI değişikliği yapıp yapmadığı kanıttan görülemiyor.",
                "summary": "Selector eskimiş; senaryo bakımı gerekiyor.",
                "most_relevant_log_lines": [
                    line for line in prompt.splitlines() if "FAILED" in line or "Exception" in line
                ][:3],
                "error_signature": "no-such-element",
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
