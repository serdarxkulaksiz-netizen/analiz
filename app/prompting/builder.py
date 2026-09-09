"""Strict prompt builder (plan.md A8) — one template per job group.

The prompt *text* lives in template files (config, not code). A profile picks
its template by name (`"prompt": "web"` -> `config/prompts/web.txt`); the
builder only renders Findings into that template's placeholders.

Every template is composed as **job-specific part + shared output contract**
(`_contract.txt`): the JSON schema, the six verdict values and the confidence
buckets are written ONCE and appended to each template. Duplicating them per
template would mean maintaining the same contract in five files, where one
silent drift breaks parsing.

Each evidence block is its own placeholder (`$test_log`, `$dom`,
`$mobile_dom`, `$browser_log`, `$build_log`, `$test_properties`), so a template
shows only the evidence that job actually produces; `$evidence_blocks` still
renders every block at once for templates that want the generic layout.

**A placeholder carries its own `=== ETİKET ===` header.** Templates must NOT
type the header themselves: an evidence that did not arrive then leaves the
prompt completely (header included) instead of leaving a heading with nothing
under it. Same for the fixed fields (`$failed_step`, `$error_message`,
`$steps`). Blank runs left behind by a missing section are collapsed, so the
prompt reads the same whether three blocks arrived or one.

`$parameter1` / `$parameter2` do not exist: those request keys decide nothing
and reach nothing (plan.md A4.2). In most runs they literally said "default" —
noise, not context — and a placeholder nobody may use is a trap, not an option.

`string.Template` is used on purpose: the contract contains a literal JSON
schema with `{}` braces, which `str.format` would mangle.
"""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from string import Template

from app.domain.findings import (
    BLOCK_BROWSER,
    BLOCK_BUILD,
    BLOCK_DOM,
    BLOCK_MOBILE_DOM,
    BLOCK_STEPS,
    BLOCK_TEST_PROPERTIES,
    DEFAULT_PROMPT_TEMPLATE,
    Findings,
)

#: Shared output contract appended to every template (not a template itself).
CONTRACT_FILE = "_contract.txt"
TEMPLATE_SUFFIX = ".txt"

#: Headers of the fixed Findings fields. In code, not config: like the evidence
#: block labels, these are format, not a per-job decision.
FIELD_LABELS: dict[str, str] = {
    "failed_step": "PATLAYAN ADIM",
    "error_message": "HATA MESAJI",
    "steps": "ADIM SONUÇLARI",
}

#: Three or more newlines -> one blank line (a dropped section leaves a hole).
_BLANK_RUN = re.compile(r"\n{3,}")


def _section(label: str, content: str) -> str:
    """`=== LABEL ===` + content, or "" when there is no content.

    The header travels WITH the content on purpose: that is what makes an
    absent evidence disappear from the prompt entirely instead of leaving a
    heading over an empty space.
    """
    return f"=== {label} ===\n{content}" if content.strip() else ""


#: Evidence block label -> its own template placeholder. A template can then
#: place each evidence exactly where it wants it, or ignore it entirely.
BLOCK_PLACEHOLDERS: dict[str, str] = {
    BLOCK_STEPS: "test_log",
    BLOCK_DOM: "dom",
    BLOCK_MOBILE_DOM: "mobile_dom",
    BLOCK_BROWSER: "browser_log",
    BLOCK_BUILD: "build_log",
    BLOCK_TEST_PROPERTIES: "test_properties",
}

#: Everything a template may reference. Anything else is a typo and fails at
#: startup — an unknown `$placeholder` would otherwise be sent to the LLM raw.
KNOWN_PLACEHOLDERS = frozenset(
    {
        "scenario_name",
        "failed_step",
        "error_message",
        "steps",
        "evidence_blocks",
        "extra_context",
        "confidence_buckets",
        *BLOCK_PLACEHOLDERS.values(),
    }
)


class PromptBuilder:
    """Renders a Findings object into its profile's single-shot prompt."""

    def __init__(self, prompts_dir: Path, confidence_buckets: list[float]) -> None:
        # Fail fast at startup: a missing contract, a missing default template
        # or an unknown placeholder are all config errors.
        contract_path = prompts_dir / CONTRACT_FILE
        if not contract_path.is_file():
            raise ValueError(
                f"Prompt contract {contract_path} is missing — it holds the JSON schema, "
                "verdict values and confidence buckets shared by every template."
            )
        contract = contract_path.read_text(encoding="utf-8")

        self._templates: dict[str, Template] = {}
        #: template name -> short hash of its exact composed text.
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

        if DEFAULT_PROMPT_TEMPLATE not in self._templates:
            raise ValueError(
                f"Prompt templates directory {prompts_dir} must contain "
                f"{DEFAULT_PROMPT_TEMPLATE}{TEMPLATE_SUFFIX} (used by every profile that does "
                "not name its own)."
            )
        self._confidence_buckets = confidence_buckets

    @property
    def template_names(self) -> set[str]:
        """Templates available to profiles."""
        return set(self._templates)

    def version_of(self, name: str) -> str:
        """Short hash of a template's exact text (template + contract).

        Stamped onto every diagnosis so a later "the answers got worse" can be
        traced to the prompt version that produced them.
        """
        return self._versions.get(name, "")

    def ensure_templates_exist(self, names: Iterable[str]) -> None:
        """Fail at startup if a profile names a template that does not exist.

        Called from the wiring root with every profile's `prompt` value, so a
        typo in `profiles.json` surfaces on boot instead of mid-analysis.
        """
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

        steps_text = "\n".join(f"- {step.name}: {step.status.value}" for step in findings.steps)
        evidence_text = "\n\n".join(
            _section(block.label, block.content)
            for block in findings.evidence_blocks
            if block.content.strip()
        )
        by_label = {block.label: block.content for block in findings.evidence_blocks}
        # A template may name an evidence this run did not produce: that
        # placeholder renders as nothing at all — header included (A5.4).
        blocks = {
            placeholder: _section(label, by_label.get(label, ""))
            for label, placeholder in BLOCK_PLACEHOLDERS.items()
        }
        buckets_text = " / ".join(str(bucket) for bucket in self._confidence_buckets)

        prompt = template.safe_substitute(
            scenario_name=findings.scenario_name,
            failed_step=_section(FIELD_LABELS["failed_step"], findings.failed_step),
            error_message=_section(FIELD_LABELS["error_message"], findings.error_message),
            steps=_section(FIELD_LABELS["steps"], steps_text),
            evidence_blocks=evidence_text,
            extra_context=findings.extra_context,
            confidence_buckets=buckets_text,
            **blocks,
        )
        # Dropped sections leave holes; without this the prompt's shape would
        # advertise exactly what is missing.
        return _BLANK_RUN.sub("\n\n", prompt).strip() + "\n"
