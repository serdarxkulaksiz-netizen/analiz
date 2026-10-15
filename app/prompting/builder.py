"""Strict prompt builder — one template per job group."""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from string import Template

from app.domain.findings import Findings
from app.evidence.checks import known_check_names

CONTRACT_FILE = "_contract.txt"
TEMPLATE_SUFFIX = ".txt"

_BLANK_RUN = re.compile(r"\n{3,}")


def _section(label: str, description: str, content: str) -> str:
    """One evidence block: header, what it is, then the content itself.

    Empty content renders nothing at all — header and description included.
    That is the point: a run where this evidence never arrived must not carry
    a sentence telling the model how to read it.
    """
    if not content.strip():
        return ""
    head = f"=== {label} ==="
    return f"{head}\n{description}\n\n{content}" if description else f"{head}\n{content}"


#: Always available, whatever the profile.
FIXED_PLACEHOLDERS = frozenset(
    {
        "scenario_name",
        "evidence_blocks",
        "extra_context",
        "confidence_buckets",
    }
)


def known_placeholders() -> frozenset[str]:
    """The fixed four plus every registered check name.

    A check's name IS its placeholder: the template writes `$<name>` where the
    computed text should land, which is how one profile puts three computed
    lines in three different places.
    """
    return FIXED_PLACEHOLDERS | known_check_names()


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
            allowed = known_placeholders()
            unknown = sorted(set(template.get_identifiers()) - allowed)
            if unknown:
                known = ", ".join(sorted(allowed))
                raise ValueError(
                    f"Prompt template {path} uses unknown placeholder(s): "
                    f"{', '.join(unknown)}. Known placeholders: {known}."
                )
            self._templates[path.stem] = template
            self._versions[path.stem] = hashlib.sha256(template.template.encode()).hexdigest()[:12]

        self._confidence_buckets = confidence_buckets

    def version_of(self, name: str) -> str:
        """Short hash of a template's exact text (template + contract)."""
        return self._versions.get(name, "")

    def checks_in(self, template_name: str) -> set[str]:
        """Which check names this template asks for (startup cross-check)."""
        template = self._templates.get(template_name)
        if template is None:
            return set()
        return set(template.get_identifiers()) & known_check_names()

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
            _section(block.label, block.description, block.content)
            for block in findings.evidence_blocks
            if block.content.strip()
        )
        buckets_text = " / ".join(str(bucket) for bucket in self._confidence_buckets)

        # A check with no text substitutes to nothing; the blank-run collapse
        # below closes the gap, so the prompt reads as if it was never there.
        values: dict[str, str] = dict.fromkeys(known_check_names(), "")
        values.update(findings.check_texts)
        prompt = template.safe_substitute(
            scenario_name=findings.scenario_name,
            evidence_blocks=evidence_text,
            extra_context=findings.extra_context,
            confidence_buckets=buckets_text,
            **values,
        )
        return _BLANK_RUN.sub("\n\n", prompt).strip() + "\n"
