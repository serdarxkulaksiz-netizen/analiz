"""Repository contract tests against FileRepository (plan.md A10)."""

from pathlib import Path

from app.persistence.file_repository import FileRepository


def test_save_get_roundtrip_with_unicode(tmp_path: Path) -> None:
    repo = FileRepository(tmp_path / "db")
    row = {"id": "r1", "explanation": "Selector eskimiş; senaryo güncellenmeli."}

    repo.save("analysis_results", "r1", row)

    assert repo.get("analysis_results", "r1") == row
    stored = (tmp_path / "db" / "analysis_results" / "r1.json").read_text(
        encoding="utf-8"
    )
    assert "eskimiş" in stored  # human-readable, not \u-escaped


def test_get_and_exists_for_missing_rows(tmp_path: Path) -> None:
    repo = FileRepository(tmp_path / "db")

    assert repo.get("runs", "missing") is None
    assert repo.exists("runs", "missing") is False
    assert repo.list("runs") == []


def test_list_returns_all_rows(tmp_path: Path) -> None:
    repo = FileRepository(tmp_path / "db")
    repo.save("runs", "a", {"id": "a"})
    repo.save("runs", "b", {"id": "b"})

    assert {row["id"] for row in repo.list("runs")} == {"a", "b"}
    assert repo.exists("runs", "a") is True


def test_save_overwrites_existing_row(tmp_path: Path) -> None:
    repo = FileRepository(tmp_path / "db")
    repo.save("runs", "a", {"status": "pending"})
    repo.save("runs", "a", {"status": "done"})

    row = repo.get("runs", "a")
    assert row is not None
    assert row["status"] == "done"
