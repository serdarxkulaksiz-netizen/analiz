"""Computed facts — small functions whose text is pasted into the prompt.

A check answers something the model cannot work out reliably on its own, and
answers it the same way every time. It is NOT evidence: the evidence is still
sent, the check only puts a short computed line beside it.

Three rules hold the mechanism together:

* The function returns the text to insert, verbatim. Nothing wraps it, nothing
  is added to it — the header, if there is one, is part of what it returns.
* An empty return inserts nothing. A check that cannot work out its answer says
  so by returning "", and the prompt reads as though the check did not exist.
* A check that raises does not stop the scenario. The evidence is untouched and
  the diagnosis is still possible; only the extra line is missing, and the run
  says why.
"""

from collections.abc import Callable

from app.evidence.base import TextEvidence

#: name -> the function that produces its text.
CHECK_REGISTRY: dict[str, "CheckFunction"] = {}


class CheckFacts:
    """What a check is given: the scenario's own facts and its evidence text."""

    def __init__(
        self,
        *,
        scenario_name: str = "",
        scenario_id: str = "",
        failed_step: str = "",
        error_text: str = "",
        profile_name: str = "",
        job_log: str = "",
        evidences: dict[str, TextEvidence] | None = None,
    ) -> None:
        self.scenario_name = scenario_name
        self.scenario_id = scenario_id
        self.failed_step = failed_step
        self.error_text = error_text
        self.profile_name = profile_name
        self.job_log = job_log
        self._evidences = evidences or {}

    def raw(self, evidence_name: str) -> str:
        """The evidence exactly as it arrived ("" when it did not arrive).

        Search in this one. The shaped text has had attributes and sections
        removed, so a miss there can mean "we removed it".
        """
        evidence = self._evidences.get(evidence_name)
        return evidence.raw_content if evidence is not None else ""

    def shaped(self, evidence_name: str) -> str:
        """The evidence after the profile's rules — what the model is shown.

        "" means the evidence did not arrive. A rule that could not cut raises
        instead of returning "": those are different states and a check that
        cannot tell them apart would report "nothing here" for a failure that
        had nothing to do with the page. The raised error is caught where every
        check failure is caught, so the run says what did not happen.
        """
        evidence = self._evidences.get(evidence_name)
        return evidence.select_content() if evidence is not None else ""

    def has(self, evidence_name: str) -> bool:
        """Did this evidence arrive at all?"""
        return bool(self.raw(evidence_name).strip())


CheckFunction = Callable[[CheckFacts], str]


def check(name: str) -> Callable[[CheckFunction], CheckFunction]:
    """Register a function under the name templates and profiles will use."""

    def register(function: CheckFunction) -> CheckFunction:
        if name in CHECK_REGISTRY:
            raise ValueError(f"check {name!r} is already registered.")
        CHECK_REGISTRY[name] = function
        return function

    return register


def known_check_names() -> set[str]:
    """Every registered check name — what a profile and a template may use."""
    return set(CHECK_REGISTRY)


def run_checks(names: list[str], facts: CheckFacts) -> tuple[dict[str, str], list[str]]:
    """Run the named checks; return their texts and the ones that failed.

    A failure never propagates: the text is left out and its reason is handed
    back, so the run can say what did not happen without losing the diagnosis.
    """
    texts: dict[str, str] = {}
    errors: list[str] = []
    for name in names:
        function = CHECK_REGISTRY.get(name)
        if function is None:
            errors.append(f"{name}: kayıtlı bir kontrol değil")
            continue
        try:
            texts[name] = function(facts) or ""
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return texts, errors


__all__ = [
    "CHECK_REGISTRY",
    "CheckFacts",
    "CheckFunction",
    "check",
    "known_check_names",
    "run_checks",
]
