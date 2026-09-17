"""Analysis profiles — job-based customization, driven by config."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.evidence.rules import Rule, RuleContext, build_rule

DEFAULT_PROFILE_NAME = "default_web"

JOB_FAILED_PROFILE_NAME = "job_failed"


class ProfileConfig(BaseModel):
    """Raw profile row as written in the config file."""

    model_config = ConfigDict(extra="forbid")

    job_ids: list[str] = []
    evidence_to_llm: list[str] = []
    evidence_to_store: list[str] = []
    rules: dict[str, list[dict]] = {}
    prompt: str
    extra_context: str = ""


class Profile:
    """A compiled profile: config plus ready-to-run rule objects."""

    def __init__(self, name: str, config: ProfileConfig) -> None:
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
            if name.startswith("_"):
                continue
            try:
                clean = {k: v for k, v in row.items() if not k.startswith("_")}
                profile = Profile(name, ProfileConfig.model_validate(clean))
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
