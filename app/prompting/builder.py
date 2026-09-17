"""Strict prompt builder — one template per job group."""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from string import Template

from app.domain.findings import Findings

CONTRACT_FILE = "_contract.txt"
TEMPLATE_SUFFIX = ".txt"

_BLANK_RUN = re.compile(r"\n{3,}")


def _section(label: str, content: str) -> str:
    """`=== LABEL ===` + content, or "" when there is no content."""
    return f"=== {label} ===\n{content}" if content.strip() else ""


KNOWN_PLACEHOLDERS = frozenset(
    {
        "scenario_name",
        "evidence_blocks",
        "extra_context",
        "confidence_buckets",
    }
)


class PromptBuilder:
    """Renders a Findings object into its profile's single-shot prompt."""

    def __init__(self, prompts_dir: Path, confidence_buckets: list[float]) -> None:
        contract_path = prompts_dir / CONTRACT_FILE
        if not contract_path.is_file():
            raise ValueError(
                f"Prompt contract {contract_path} is missing — it holds the JSON schema, "
                "verdict values and confidence buckets shared by every template."
            )
        contract = contract_path.read_text(encoding="utf-8")

        self._templates: dict[str, Template] = {}
        self._versions: dict[str, str] = {}
        for path in sorted(prompts_dir.glob(f"*{TEMPLATE_SUFFIX}")):
            if path.name == CONTRACT_FILE:
                continue
            template = Template(f"{path.read_text(encoding='utf-8').rstrip()}\n\n{contract}")
            unknown = sorted(set(template.get_identifiers()) - KNOWN_PLACEHOLDERS)
            if unknown:
                known = ", ".join(sorted(KNOWN_PLACEHOLDERS))
                raise ValueError(
                    f"Prompt template {path} uses unknown placeholder(s): "
                    f"{', '.join(unknown)}. Known placeholders: {known}."
                )
            self._templates[path.stem] = template
            self._versions[path.stem] = hashlib.sha256(template.template.encode()).hexdigest()[:12]

        self._confidence_buckets = confidence_buckets

    @property
    def template_names(self) -> set[str]:
        """Templates available to profiles."""
        return set(self._templates)

    def version_of(self, name: str) -> str:
        """Short hash of a template's exact text (template + contract)."""
        return self._versions.get(name, "")

    def ensure_templates_exist(self, names: Iterable[str]) -> None:
        """Fail at startup if a profile names a template that does not exist."""
        missing = sorted({name for name in names if name not in self._templates})
        if missing:
            known = ", ".join(sorted(self._templates))
            raise ValueError(
                f"Profile(s) ask for unknown prompt template(s): {', '.join(missing)}. "
                f"Available templates: {known}."
            )

    def build(self, findings: Findings) -> str:
        """Build the full prompt for one failed scenario."""
        template = self._templates.get(findings.prompt_template)
        if template is None:
            known = ", ".join(sorted(self._templates))
            raise ValueError(
                f"Unknown prompt template {findings.prompt_template!r}. Available: {known}."
            )

        evidence_text = "\n\n".join(
            _section(block.label, block.content)
            for block in findings.evidence_blocks
            if block.content.strip()
        )
        buckets_text = " / ".join(str(bucket) for bucket in self._confidence_buckets)

        prompt = template.safe_substitute(
            scenario_name=findings.scenario_name,
            evidence_blocks=evidence_text,
            extra_context=findings.extra_context,
            confidence_buckets=buckets_text,
        )
        return _BLANK_RUN.sub("\n\n", prompt).strip() + "\n"
