"""Strict prompt builder (plan.md A7).

The prompt *text* lives in a template file (config, not code). The builder
only renders Findings into the template's placeholders: role, task, platform
info, organized evidence, step-by-step reasoning, hard negative constraints
and the mandatory JSON schema are all in the template.

`string.Template` is used on purpose: the template contains a literal JSON
schema with `{}` braces, which `str.format` would mangle.
"""

from pathlib import Path
from string import Template

from app.domain.findings import Findings


class PromptBuilder:
    """Renders a Findings object into the single-shot analysis prompt."""

    def __init__(self, template_path: Path, confidence_buckets: list[float]) -> None:
        # Fail fast at startup if the template is missing/misconfigured.
        self._template = Template(template_path.read_text(encoding="utf-8"))
        self._confidence_buckets = confidence_buckets

    def build(self, findings: Findings) -> str:
        """Build the full prompt for one failed scenario."""
        steps_text = "\n".join(
            f"- {step.name}: {step.status.value}" for step in findings.steps
        )
        evidence_text = "\n\n".join(
            f"=== {block.label} ===\n{block.content}"
            for block in findings.evidence_blocks
            if block.content
        )
        missing_text = (
            "\n".join(f"- {name}" for name in findings.missing_evidence)
            if findings.missing_evidence
            else "(eksik kanıt yok)"
        )
        buckets_text = " / ".join(str(bucket) for bucket in self._confidence_buckets)

        return self._template.safe_substitute(
            platform=findings.platform.value,
            bank=findings.bank,
            scenario_name=findings.scenario_name,
            failed_step=findings.failed_step,
            error_message=findings.error_message,
            steps=steps_text,
            missing_evidence=missing_text,
            evidence_blocks=evidence_text,
            confidence_buckets=buckets_text,
        )
