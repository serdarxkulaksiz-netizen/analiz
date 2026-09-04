"""Startup contract: config is strict, and importing the app is side-effect free.

Two traps these tests lock down, both found while hardening the project:

1. An unknown key in `.env` used to be ignored, so a typo or a renamed setting
   (VISIUMGO_JENKINS_LOG_PATH after the build-log rename) left the feature
   silently off with no warning anywhere.
2. `app/main.py` built the FastAPI app at import time, so merely importing it
   read the developer's real `.env` — making the test suite depend on whichever
   `.env` happened to be on the machine.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.config import Settings, get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_unknown_env_key_fails_with_a_helpful_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=abc\nVISIUMGO_JENKINS_LOG_PATH=/eski/yol\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    with pytest.raises(ValueError) as excinfo:
        get_settings()

    message = str(excinfo.value)
    assert "VISIUMGO_JENKINS_LOG_PATH" in message  # names the offending key
    assert ".env.example" in message  # and where to look it up
    get_settings.cache_clear()


def test_known_keys_still_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=abc\nMAX_CONCURRENCY=7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.llm_model == "abc" and settings.max_concurrency == 7
    get_settings.cache_clear()


def test_unrelated_os_env_vars_are_not_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only the `.env` file's own keys are checked; the machine's environment
    # (PATH, HOMEBREW_PREFIX, CI vars...) must never break startup.
    (tmp_path / ".env").write_text("LLM_MODEL=abc\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOME_UNRELATED_TOOL_VAR", "1")
    get_settings.cache_clear()

    assert get_settings().llm_model == "abc"
    get_settings.cache_clear()


def test_importing_main_is_side_effect_free(tmp_path: Path) -> None:
    """Import must not read `.env`; only asking for `app` may (PEP 562).

    Proven the honest way: run in a directory whose `.env` is INVALID. If the
    import itself read config, it would fail. Accessing `app` then must fail —
    that is what shows config is read lazily, at the moment it is needed.
    """
    (tmp_path / ".env").write_text("GECERSIZ_ANAHTAR=1\n", encoding="utf-8")
    script = (
        "import app.main;"
        "print('IMPORT_OK');"
        "\ntry:\n    app.main.app\n"
        "except ValueError as exc:\n"
        "    print('LAZY_OK' if 'GECERSIZ_ANAHTAR' in str(exc) else 'WRONG')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )

    assert "IMPORT_OK" in result.stdout, result.stderr  # import needed no config
    assert "LAZY_OK" in result.stdout, result.stdout + result.stderr  # app did


def test_uvicorn_style_app_lookup_still_works(settings: Settings) -> None:
    """`uvicorn app.main:app` does getattr(module, "app") — keep that working."""
    import app.main as main

    assert isinstance(main.create_app(settings), FastAPI)
    with pytest.raises(AttributeError):
        _ = main.boyle_bir_sey_yok  # noqa: B018 — erişimin kendisi test ediliyor
