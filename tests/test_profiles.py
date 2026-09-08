"""Profile registry tests: job_id mapping, manual override, fail-fast config."""

import json
from pathlib import Path

import pytest

from app.evidence.profiles import ProfileRegistry
from app.evidence.registry import EvidenceRegistry
from app.extraction.evidence_extractor import EvidenceExtractor
from app.prompting.builder import PromptBuilder
from tests.test_extraction import _scenario  # reuse the sample scenario

_CONFIG = {
    "default": {
        "evidence_to_llm": ["TestLogEvidence", "HtmlEvidence", "BrowserLogEvidence"],
        "evidence_to_store": ["TestLogEvidence", "HtmlEvidence"],
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


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _registry(tmp_path: Path, data: dict | None = None) -> ProfileRegistry:
    return ProfileRegistry(_write(tmp_path, data or _CONFIG))


def test_job_id_selects_profile(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    assert registry.get(job_id="1350").name == "D_dom_temiz"
    assert registry.get(job_id="902").name == "B_sadece_testlog"


def test_unknown_job_id_falls_back_to_default(tmp_path: Path) -> None:
    assert _registry(tmp_path).get(job_id="9999").name == "default"


def test_parameter1_overrides_job_mapping(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    chosen = registry.get(job_id="1350", parameter1="B_sadece_testlog")
    assert chosen.name == "B_sadece_testlog"


def test_default_parameter1_does_not_override(tmp_path: Path) -> None:
    # "default" is the API's default value => means "no override".
    registry = _registry(tmp_path)
    assert registry.get(job_id="1350", parameter1="default").name == "D_dom_temiz"


def test_unknown_profile_name_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        _registry(tmp_path).get(job_id="1350", parameter1="yok-boyle")


def test_missing_default_profile_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="default"):
        _registry(tmp_path, {"onlyone": {"job_ids": ["1"]}})


def test_duplicate_job_id_fails_fast(tmp_path: Path) -> None:
    data = {
        "default": {},
        "a": {"job_ids": ["7"]},
        "b": {"job_ids": ["7"]},
    }
    with pytest.raises(ValueError, match="claimed by both"):
        _registry(tmp_path, data)


def test_bad_rule_config_fails_fast(tmp_path: Path) -> None:
    data = {"default": {"rules": {"HtmlEvidence": [{"type": "yok_boyle_kural"}]}}}
    with pytest.raises(ValueError, match="Unknown rule type"):
        _registry(tmp_path, data)


def test_profile_limits_prompt_evidence_end_to_end(tmp_path: Path) -> None:
    # Job 901 -> only test.log reaches the prompt (config only, no code).
    extractor = EvidenceExtractor(EvidenceRegistry(), _registry(tmp_path))

    findings = extractor.extract(_scenario(), job_id="901")

    assert findings.profile_name == "B_sadece_testlog"
    labels = [b.label for b in findings.evidence_blocks]
    assert "ADIMLAR" in labels  # test.log in
    assert "DOM" not in labels and "BROWSER LOG" not in labels
    assert "HATA" in labels  # error block is profile-independent


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
        "default": {"evidence_to_llm": ["TestLogEvidence"], "evidence_to_store": []},
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

    labels = [b.label for b in findings.evidence_blocks]
    assert "BUILD LOG" in labels  # build log in
    assert "ADIMLAR" not in labels and "DOM" not in labels  # others out

    console = next(b for b in findings.evidence_blocks if b.label == "BUILD LOG")
    assert "bizim adım FAILED" in console.content  # only this scenario's part
    assert "baska adım" not in console.content
    assert "ucuncu adım" not in console.content
    # Trimming is visible, never silent.
    assert findings.truncated is True
    assert "BuildLogEvidence" in findings.truncated_note


def test_profile_picks_its_prompt_template(tmp_path: Path) -> None:
    """A job group chooses its own prompt; unnamed profiles get `default`."""
    config = {
        "default": {"evidence_to_llm": ["TestLogEvidence"]},
        "mobil_bankacilik": {
            "job_ids": ["223", "234"],
            "prompt": "mobile",
            "evidence_to_llm": ["TestLogEvidence"],
            "extra_context": "Bu joblar mobil bankacılık joblarıdır.",
        },
    }
    registry = _registry(tmp_path, config)

    assert registry.get(job_id="223").prompt == "mobile"
    assert registry.get(job_id="bilinmeyen").prompt == "default"
    # The wiring root asks for this set to validate it against the templates.
    assert registry.prompt_names() == {"default", "mobile"}


def test_findings_carry_the_profiles_prompt_template(tmp_path: Path) -> None:
    """Extraction stamps the template on Findings — that is how ring 3 knows."""
    config = {
        "default": {"evidence_to_llm": ["TestLogEvidence"]},
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


def test_report_shows_when_scenario_slicing_did_not_match(tmp_path: Path) -> None:
    """The build-log risk, made visible instead of silent.

    `keep_scenario_section` leaves the text untouched when its marker is not
    found (deliberate: no silent loss). The cost is that the WHOLE job log then
    goes into every scenario's prompt. The report says so: the block was not
    trimmed and is as large as the raw log.
    """
    job_log = "\n".join(f"satır {i}" for i in range(200))
    config = {
        "default": {"evidence_to_llm": ["TestLogEvidence"]},
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

    block = next(row for row in findings.evidence_report.blocks if row.label == "BUILD LOG")
    assert block.trimmed is False  # the marker was never found
    assert block.chars == len(job_log)  # so the entire job log went to the prompt
    assert findings.truncated is False


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
        "default": {"evidence_to_llm": ["TestLogEvidence"]},
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

    block = next(b for b in findings.evidence_blocks if b.label == "BUILD LOG")
    assert "bizim satır FAILED" in block.content
    assert "baska satır" not in block.content and "ucuncu satır" not in block.content
    report = next(r for r in findings.evidence_report.blocks if r.label == "BUILD LOG")
    assert report.trimmed is True  # slicing actually happened


def test_example_profiles_file_stays_valid() -> None:
    """`config/profiles.example.json` is copy-paste documentation — it must load.

    An example that has rotted (unknown rule type, unknown prompt template, a
    job_id claimed twice) is worse than no example: it gets copied verbatim to
    the work PC and fails there, on a machine where nobody debugs.
    """
    path = Path("config/profiles.example.json")
    registry = ProfileRegistry(path)
    builder = PromptBuilder(Path("config/prompts"), [0.1, 0.25, 0.5, 0.75, 0.99])

    builder.ensure_templates_exist(registry.prompt_names())  # raises if a name is wrong
    assert registry.get(job_id="889").prompt == "buildlog"
    assert registry.get(job_id="1321").evidence_to_llm == [
        "TestLogEvidence",
        "HtmlEvidence",
        "BrowserLogEvidence",
    ]
