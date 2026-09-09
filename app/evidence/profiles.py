"""Analysis profiles — job-based customization, driven by config.

A profile says, for a group of jobs, three things:
  - `evidence_to_store` — which attachments are DOWNLOADED and written to
    `database/` (an attachment in no list is never fetched at all),
  - `evidence_to_llm`   — which of them reach the prompt,
  - `rules`             — how each one is trimmed on the way to the prompt
    (the stored copy stays whole).
Plus the prompt template and any extra prompt context. Adding a job's
behaviour = a config row in `config/profiles.json`, no code.

Resolution order (no `if job_id ==` anywhere — dict/registry lookups):
    1. a `forced` profile name from the caller — the job-level state of a run
       (a `FAILED` job is analyzed with `job_failed`, whatever job it is) or a
       tool that must run with a specific profile (`tools.inspect_run`)
    2. the job_id appears in some profile's `job_ids`
    3. the mandatory `default_web` profile

The request's `parameter1`/`parameter2` take NO part in this (nor in anything
else the code decides): they are recorded on the run and shown by the API,
nothing more.

Everything is validated and compiled at startup: unknown rule types, bad
regexes, a job_id claimed by two profiles, prompted-but-not-stored evidence and
a missing `default_web`/`job_failed` profile all fail immediately rather than
mid-analysis.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from app.domain.findings import DEFAULT_PROMPT_TEMPLATE
from app.evidence.rules import Rule, RuleContext, build_rule

#: Fallback profile: the one a job that matches nothing is analyzed with. The
#: name says what it is — a web-shaped default — so nobody reads "default" as
#: "neutral".
DEFAULT_PROFILE_NAME = "default_web"

#: Profile every scenario of a job-level FAILED run is analyzed with, no matter
#: which job it is: when the job itself failed, its `job_ids` profile describes
#: a normal run that never happened. Mandatory, like `default`, so the branch
#: can never land on a missing profile mid-analysis.
JOB_FAILED_PROFILE_NAME = "job_failed"


class ProfileConfig(BaseModel):
    """Raw profile row as written in the config file."""

    job_ids: list[str] = []
    #: Evidence that reaches the prompt. Must be a subset of `evidence_to_store`
    #: — what is not downloaded cannot be prompted.
    evidence_to_llm: list[str] = []
    #: Evidence that is downloaded and stored. Anything absent here is NOT
    #: fetched from VisiumGo at all.
    evidence_to_store: list[str] = []
    rules: dict[str, list[dict]] = {}
    #: Prompt template name (a file in the prompts dir, without .txt). The
    #: existence check happens at startup in the wiring root, which is the only
    #: place that knows both the profiles and the available templates.
    prompt: str = DEFAULT_PROMPT_TEMPLATE
    extra_context: str = ""


class Profile:
    """A compiled profile: config plus ready-to-run rule objects."""

    def __init__(self, name: str, config: ProfileConfig) -> None:
        # Prompting an evidence that is never downloaded would silently produce
        # an empty block, and the config would read as if it were sent. Fail
        # here instead: this is a config error, not a runtime condition.
        missing = sorted(set(config.evidence_to_llm) - set(config.evidence_to_store))
        if missing:
            raise ValueError(
                f"evidence_to_llm içindeki {', '.join(missing)} evidence_to_store'da yok — "
                "indirilmeyen kanıt prompt'a giremez."
            )
        self.name = name
        self.job_ids = config.job_ids
        self.evidence_to_llm = config.evidence_to_llm
        self.evidence_to_store = config.evidence_to_store
        self.prompt = config.prompt
        self.extra_context = config.extra_context
        self._rules: dict[str, list[Rule]] = {
            evidence_name: [build_rule(row) for row in rows]
            for evidence_name, rows in config.rules.items()
        }

    def rules_for(self, evidence_name: str) -> list[Rule]:
        """Content rules for one evidence type (empty = passthrough)."""
        return self._rules.get(evidence_name, [])

    @property
    def wanted_evidence(self) -> set[str]:
        """Evidence this profile needs at all — i.e. what is worth downloading."""
        return set(self.evidence_to_llm) | set(self.evidence_to_store)


class ProfileRegistry:
    """Loads profiles from config and resolves them per request."""

    def __init__(self, config_path: Path) -> None:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        self._profiles: dict[str, Profile] = {}
        self._by_job_id: dict[str, Profile] = {}

        for name, row in data.items():
            # JSON has no comments, so a `_`-prefixed key is one: it documents
            # the file next to the thing it documents instead of in a README
            # nobody opens while editing config.
            if name.startswith("_"):
                continue
            try:
                profile = Profile(name, ProfileConfig.model_validate(row))
            except ValueError as exc:
                raise ValueError(f"profile {name!r}: {exc}") from exc
            self._profiles[name] = profile
            for job_id in profile.job_ids:
                owner = self._by_job_id.get(job_id)
                if owner is not None:
                    raise ValueError(
                        f"job_id {job_id!r} is claimed by both {owner.name!r} "
                        f"and {name!r} in {config_path}."
                    )
                self._by_job_id[job_id] = profile

        for required in (DEFAULT_PROFILE_NAME, JOB_FAILED_PROFILE_NAME):
            if required not in self._profiles:
                raise ValueError(
                    f'profiles config {config_path} must contain a "{required}" profile.'
                )

    def evidence_names(self) -> set[str]:
        """Every evidence name the profiles mention (startup validation)."""
        names: set[str] = set()
        for profile in self._profiles.values():
            names |= profile.wanted_evidence
        return names

    def prompt_names(self) -> set[str]:
        """Every prompt template name the profiles ask for (startup check)."""
        return {profile.prompt for profile in self._profiles.values()}

    def get(self, job_id: str = "", forced: str = "") -> Profile:
        """Resolve the profile for this run (see module docstring for order)."""
        if forced:
            profile = self._profiles.get(forced)
            if profile is None:
                known = ", ".join(sorted(self._profiles))
                raise ValueError(f"Unknown profile {forced!r}. Known profiles: {known}")
            return profile
        if job_id and job_id in self._by_job_id:
            return self._by_job_id[job_id]
        return self._profiles[DEFAULT_PROFILE_NAME]


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "JOB_FAILED_PROFILE_NAME",
    "Profile",
    "ProfileConfig",
    "ProfileRegistry",
    "RuleContext",
]
