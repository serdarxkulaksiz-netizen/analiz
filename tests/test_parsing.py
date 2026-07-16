"""Parsing contract tests: `_try_json` only (plan.md Halka 5)."""

from app.parsing.json_parser import _try_json


def test_plain_json_object() -> None:
    assert _try_json('{"verdict": "test_maintenance"}') == {
        "verdict": "test_maintenance"
    }


def test_markdown_fenced_json() -> None:
    text = '```json\n{"confidence": 0.75}\n```'
    assert _try_json(text) == {"confidence": 0.75}


def test_json_surrounded_by_prose() -> None:
    text = 'İşte analizim:\n{"summary": "Selector eskimiş."}\nUmarım yardımcı olur.'
    assert _try_json(text) == {"summary": "Selector eskimiş."}


def test_garbage_returns_none() -> None:
    assert _try_json("model çıktı üretemedi, üzgünüm") is None


def test_non_object_json_returns_none() -> None:
    assert _try_json("[1, 2, 3]") is None
    assert _try_json('"sadece string"') is None


def test_empty_string_returns_none() -> None:
    assert _try_json("") is None
