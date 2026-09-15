"""Profile registry tests: job_id mapping, manual override, fail-fast config."""

from pathlib import Path

import pytest

from app.evidence.profiles import JOB_FAILED_PROFILE_NAME, ProfileRegistry
from app.evidence.registry import EvidenceRegistry, known_evidence_names
from app.extraction.evidence_extractor import EvidenceExtractor
from app.prompting.builder import PromptBuilder
from tests.conftest import write_profiles
from tests.test_extraction import _scenario  # reuse the sample scenario

_CONFIG = {
    "default_web": {
        "evidence_to_llm": ["TestLogEvidence", "HtmlEvidence"],
        "evidence_to_store": ["TestLogEvidence", "HtmlEvidence", "WebScreenshotEvidence"],
    },
    "B_sadece_testlog": {
        "job_ids": ["901", "902"],
        "evidence_to_llm": ["TestLogEvidence"],
        "evidence_to_store": ["TestLogEvidence"],
    },
    "D_dom_temiz": {
        "job_ids": ["1350"],
        "evidence_to_llm": ["TestLogEvidence", "HtmlEvidence"],
        "evidence_to_store": ["TestLogEvidence", "HtmlEvidence"],
        "rules": {"HtmlEvidence": [{"type": "strip_tags", "tags": ["script"]}]},
        "extra_context": "Bu projede X kullanılıyor.",
    },
}


def _write(tmp_path: Path, data: dict, *, complete: bool = False) -> Path:
    return write_profiles(tmp_path / "profiles.json", data, complete=complete)


def _registry(
    tmp_path: Path, data: dict | None = None, *, complete: bool = False
) -> ProfileRegistry:
    return ProfileRegistry(_write(tmp_path, data or _CONFIG, complete=complete))


def test_job_id_selects_profile(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    assert registry.get(job_id="1350").name == "D_dom_temiz"
    assert registry.get(job_id="902").name == "B_sadece_testlog"


def test_unknown_job_id_falls_back_to_default(tmp_path: Path) -> None:
    assert _registry(tmp_path).get(job_id="9999").name == "default_web"


def test_forced_profile_overrides_job_mapping(tmp_path: Path) -> None:
    """The only override there is: the job-level FAILED branch.

    `ProfileRegistry` still takes a name from its caller, but inside the
    service that caller is the run's own state — nothing the request says can
    reach it.
    """
    registry = _registry(tmp_path)
    assert registry.get(job_id="1350", forced="B_sadece_testlog").name == "B_sadece_testlog"


def test_unknown_forced_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        _registry(tmp_path).get(job_id="1350", forced="yok-boyle")


def test_missing_default_profile_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="default_web"):
        _registry(tmp_path, {"onlyone": {"job_ids": ["1"]}}, complete=True)


def test_missing_job_failed_profile_fails_fast(tmp_path: Path) -> None:
    """A config without `job_failed` cannot serve a job-level FAILED run."""
    with pytest.raises(ValueError, match="job_failed"):
        _registry(tmp_path, {"default_web": {}}, complete=True)


def test_duplicate_job_id_fails_fast(tmp_path: Path) -> None:
    data = {
        "default_web": {},
        "a": {"job_ids": ["7"]},
        "b": {"job_ids": ["7"]},
    }
    with pytest.raises(ValueError, match="claimed by both"):
        _registry(tmp_path, data)


def test_bad_rule_config_fails_fast(tmp_path: Path) -> None:
    data = {"default_web": {"rules": {"HtmlEvidence": [{"type": "yok_boyle_kural"}]}}}
    with pytest.raises(ValueError, match="Unknown rule type"):
        _registry(tmp_path, data)


def test_profile_limits_prompt_evidence_end_to_end(tmp_path: Path) -> None:
    # Job 901 -> only test.log reaches the prompt (config only, no code).
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path))

    findings = extractor.extract(_scenario(), job_id="901")

    assert findings.profile_name == "B_sadece_testlog"
    assert [b.evidence_name for b in findings.evidence_blocks] == ["TestLogEvidence"]


def test_extra_context_flows_to_findings(tmp_path: Path) -> None:
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path))
    findings = extractor.extract(_scenario(), job_id="1350")
    assert findings.extra_context == "Bu projede X kullanılıyor."


_JOB_LOG = """[jenkins] build started
Scenario: Baska senaryo
  baska adım FAILED
Scenario: Senaryo
  bizim adım FAILED
Scenario: Ucuncu senaryo
  ucuncu adım"""


def test_job_c_only_build_log_sliced_per_scenario(tmp_path: Path) -> None:
    """Job C: sadece build log, ve yalnız bu senaryonun bölümü."""
    config = {
        "default_web": {"evidence_to_llm": [], "evidence_to_store": []},
        "C_build_log_dilim": {
            "job_ids": ["1204"],
            "evidence_to_llm": ["BuildLogEvidence"],
            "evidence_to_store": ["BuildLogEvidence"],
            "rules": {
                "BuildLogEvidence": [
                    {
                        "type": "keep_scenario_section",
                        "start": "Scenario: {scenario_name}",
                        "end": "Scenario: ",
                    }
                ]
            },
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    findings = extractor.extract(_scenario(), job_id="1204", build_log=_JOB_LOG)

    # Only the build log reaches the prompt; the scenario's own files do not.
    assert [b.evidence_name for b in findings.evidence_blocks] == ["BuildLogEvidence"]

    console = findings.evidence_blocks[0]
    assert "bizim adım FAILED" in console.content  # only this scenario's part
    assert "baska adım" not in console.content
    assert "ucuncu adım" not in console.content
    # Trimming is visible, never silent.
    assert findings.truncated is True
    assert "BuildLogEvidence" in findings.truncated_note


def test_profile_picks_its_prompt_template(tmp_path: Path) -> None:
    """A job group chooses its own prompt; unnamed profiles get `default`."""
    config = {
        "default_web": {"evidence_to_llm": ["TestLogEvidence"]},
        "mobil_bankacilik": {
            "job_ids": ["223", "234"],
            "prompt": "mobile",
            "evidence_to_llm": ["TestLogEvidence"],
            "extra_context": "Bu joblar mobil bankacılık joblarıdır.",
        },
    }
    registry = _registry(tmp_path, config)

    assert registry.get(job_id="223").prompt == "mobile"
    assert registry.get(job_id="bilinmeyen").prompt == "default"  # şablon adı, profil değil
    # The wiring root asks for this set to validate it against the templates.
    assert registry.prompt_names() == {"default", "mobile"}


def test_findings_carry_the_profiles_prompt_template(tmp_path: Path) -> None:
    """Extraction stamps the template on Findings — that is how ring 3 knows."""
    config = {
        "default_web": {"evidence_to_llm": ["TestLogEvidence"]},
        "sadece_buildlog": {
            "job_ids": ["889", "890"],
            "prompt": "buildlog",
            "evidence_to_llm": ["BuildLogEvidence"],
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    findings = extractor.extract(_scenario(), job_id="889", build_log="BUILD FAILED")

    assert findings.prompt_template == "buildlog"
    assert findings.profile_name == "sadece_buildlog"


def test_slicing_that_cannot_match_fails_the_scenario_instead_of_flooding_it(
    tmp_path: Path,
) -> None:
    """The profile said "this scenario's section". It could not be found.

    Sending the untrimmed job log is not a lesser version of that instruction —
    it is the opposite of it, repeated once per scenario. So the evidence
    produces NO block, and the reason is recorded where the scenario's own row
    will carry it.
    """
    job_log = "\n".join(f"satır {i}" for i in range(200))
    config = {
        "default_web": {"evidence_to_llm": ["TestLogEvidence"]},
        "buildlog_jobs": {
            "job_ids": ["889"],
            "prompt": "buildlog",
            "evidence_to_llm": ["BuildLogEvidence"],
            "rules": {
                "BuildLogEvidence": [
                    {
                        "type": "keep_scenario_section",
                        "start": "> Scenario [{scenario_name}] started",
                        "end": "beforeScenario:",
                    }
                ]
            },
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    findings = extractor.extract(_scenario(), job_id="889", build_log=job_log)

    assert findings.evidence_blocks == []  # nothing reached the prompt
    (error,) = findings.evidence_report.rule_errors
    assert error.startswith("BuildLogEvidence: keep_scenario_section")
    assert "> Scenario [Senaryo] started" in error  # the marker it looked for


def test_report_shows_a_successful_scenario_slice(tmp_path: Path) -> None:
    """The same rule against the real build.log format (verified 2026-09-01)."""
    job_log = (
        "beforeScenario:63 - [2]  > Scenario [Baska] started\n"
        "baska satır\n"
        "beforeScenario:63 - [2]  > Scenario [Senaryo] started\n"
        "bizim satır FAILED\n"
        "beforeScenario:63 - [2]  > Scenario [Ucuncu] started\n"
        "ucuncu satır\n"
    )
    config = {
        "default_web": {"evidence_to_llm": ["TestLogEvidence"]},
        "buildlog_jobs": {
            "job_ids": ["889"],
            "prompt": "buildlog",
            "evidence_to_llm": ["BuildLogEvidence"],
            # No markers here on purpose: they are a property of the log format,
            # not a per-job decision, so the profile only asks for the rule.
            "rules": {"BuildLogEvidence": [{"type": "keep_scenario_section"}]},
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    findings = extractor.extract(_scenario(), job_id="889", build_log=job_log)

    block = next(b for b in findings.evidence_blocks if b.evidence_name == "BuildLogEvidence")
    assert "bizim satır FAILED" in block.content
    assert "baska satır" not in block.content and "ucuncu satır" not in block.content
    report = next(r for r in findings.evidence_report.blocks if r.label.startswith("build.log · "))
    assert report.trimmed is True  # slicing actually happened


def test_shipped_profiles_config_stays_valid() -> None:
    """`config/profiles.json` is what actually ships — it must load and line up.

    A config that has rotted (unknown rule type, unknown prompt template, a
    job_id claimed twice, prompted evidence that is never downloaded) would
    otherwise only fail on the work PC, on a machine where nobody debugs.
    """
    registry = ProfileRegistry(Path("config/profiles.json"))
    builder = PromptBuilder(Path("config/prompts"), [0.1, 0.25, 0.5, 0.75, 0.99])

    builder.ensure_templates_exist(registry.prompt_names())  # raises if a name is wrong
    assert registry.evidence_names() <= known_evidence_names()

    # The three profiles the system relies on by name.
    assert registry.get(job_id="bilinmeyen-job").name == "default_web"
    assert registry.get(forced=JOB_FAILED_PROFILE_NAME).name == JOB_FAILED_PROFILE_NAME
    test_all = registry.get(forced="test_all")
    # The inspection profile has to fetch everything, or the tool built on it
    # would report "missing" for files nobody asked for.
    assert test_all.wanted_evidence == known_evidence_names()


def test_profile_alone_decides_what_reaches_the_prompt(tmp_path: Path) -> None:
    """The bug this locks out: a profile asked for build.log and it vanished.

    `web.txt` had placeholders for test.log / DOM / browser log and none for the
    build log, so a profile that listed `BuildLogEvidence` produced a prompt
    with the template's instructions and no evidence in it — silently, with the
    config reading as if the log were being sent. Templates name no evidence
    now, so adding one is a single line in `profiles.json`.
    """
    config = {
        "default_web": {
            # A web job that ALSO wants the job log — the exact combination the
            # template could not express before.
            "prompt": "web",
            "evidence_to_llm": ["TestLogEvidence", "BuildLogEvidence"],
            "evidence_to_store": ["TestLogEvidence", "BuildLogEvidence"],
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))
    builder = PromptBuilder(Path("config/prompts"), [0.1, 0.25, 0.5, 0.75, 0.99])

    findings = extractor.extract(_scenario(), build_log=_JOB_LOG)
    prompt = builder.build(findings)

    assert "=== test.log · " in prompt
    assert "=== build.log · " in prompt  # reached the prompt with no template edit
    assert "bizim adım FAILED" in prompt
    # And the profile's order is the prompt's order.
    assert prompt.index("=== test.log · ") < prompt.index("=== build.log · ")


def test_build_log_is_reported_as_a_job_log_not_an_attachment(tmp_path: Path) -> None:
    """`evidence_report.attachments` answers "what did VisiumGo send?".

    The build log arrives from `/api/runs/{run_id}/logs`, never from a
    scenario's `attachments[]`. It used to be wrapped in a synthetic
    `Attachment` and listed there anyway, so the report claimed a file the API
    had never sent.
    """
    config = {
        "default_web": {
            "evidence_to_llm": ["BuildLogEvidence"],
            "evidence_to_store": ["BuildLogEvidence"],
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    report = extractor.extract(_scenario(), build_log=_JOB_LOG).evidence_report

    listed = {row.file_name for row in report.attachments}
    assert not [name for name in listed if "build" in name]
    assert all("/" in name for name in listed)  # every row is a real VisiumGo fileName

    assert report.job_log.wanted is True
    assert report.job_log.goes_to_llm is True
    assert report.job_log.chars == len(_JOB_LOG)
    assert report.job_log.source == "/api/runs/{run_id}/logs"
    assert report.job_log.error == ""


def test_job_log_report_tells_wanted_from_broken(tmp_path: Path) -> None:
    """ "Profile did not ask" and "the fetch failed" must never look alike."""
    config = {
        "default_web": {
            "evidence_to_llm": ["TestLogEvidence"],
            "evidence_to_store": ["TestLogEvidence"],
        },
    }
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    not_wanted = extractor.extract(_scenario()).evidence_report.job_log
    assert not_wanted.wanted is False and not_wanted.error == ""

    config["default_web"]["evidence_to_llm"] = ["TestLogEvidence", "BuildLogEvidence"]
    config["default_web"]["evidence_to_store"] = ["TestLogEvidence", "BuildLogEvidence"]
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path, config))

    broken = extractor.extract(_scenario(), build_log="", build_log_error="404").evidence_report
    assert broken.job_log.wanted is True
    assert broken.job_log.chars == 0
    assert broken.job_log.error == "404"
