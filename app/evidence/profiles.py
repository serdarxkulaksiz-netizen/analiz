"""Analysis profiles — job-based customization, driven by config.

A profile says, for a group of jobs: which evidence reaches the LLM, which is
stored, what content rules shape each evidence, and any extra prompt context.
Adding a job's behaviour = a config row in `config/profiles.json`, no code.

Resolution order (no `if job_id ==` anywhere — dict/registry lookups):
    0. a `forced` profile name from the caller (today: the job-level state of
       a run — a `FAILED` job is analyzed with `job_failed`, whatever job it is)
    1. `parameter1` names a profile explicitly (manual override; unknown -> error)
    2. the job_id appears in some profile's `job_ids`
    3. the mandatory `default` profile

`parameter1 == "default"` (the API's default value) means "no override", so the
job mapping still applies. Everything is validated and compiled at startup:
unknown rule types, bad regexes, a job_id claimed by two profiles and a missing
`default`/`job_failed` profile all fail immediately rather than mid-analysis.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from app.domain.findings import DEFAULT_PROMPT_TEMPLATE
from app.evidence.rules import Rule, RuleContext, build_rule

DEFAULT_PROFILE_NAME = "default"

#: Profile every scenario of a job-level FAILED run is analyzed with, no matter
#: which job it is: when the job itself failed, its `job_ids` profile describes
#: a normal run that never happened. Mandatory, like `default`, so the branch
#: can never land on a missing profile mid-analysis.
JOB_FAILED_PROFILE_NAME = "job_failed"


class ProfileConfig(BaseModel):
    """Raw profile row as written in the config file."""

    job_ids: list[str] = []
    evidence_to_llm: list[str] = []
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


class ProfileRegistry:
    """Loads profiles from config and resolves them per request."""

    def __init__(self, config_path: Path) -> None:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        self._profiles: dict[str, Profile] = {}
        self._by_job_id: dict[str, Profile] = {}

        for name, row in data.items():
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

    def prompt_names(self) -> set[str]:
        """Every prompt template name the profiles ask for (startup check)."""
        return {profile.prompt for profile in self._profiles.values()}

    def get(self, job_id: str = "", parameter1: str = "", forced: str = "") -> Profile:
        """Resolve the profile for this run (see module docstring for order)."""
        if forced:
            profile = self._profiles.get(forced)
            if profile is None:
                known = ", ".join(sorted(self._profiles))
                raise ValueError(f"Unknown profile {forced!r}. Known profiles: {known}")
            return profile
        if parameter1 and parameter1 != DEFAULT_PROFILE_NAME:
            profile = self._profiles.get(parameter1)
            if profile is None:
                known = ", ".join(sorted(self._profiles))
                raise ValueError(f"Unknown profile {parameter1!r}. Known profiles: {known}")
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
