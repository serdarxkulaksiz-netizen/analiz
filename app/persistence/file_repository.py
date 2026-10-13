"""File-based Repository — diagnoses that outlive the process."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.persistence.repository import Repository

RUN_KEY = "analyzer_run_id"


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


class FileRepository(Repository):
    """Stores every row as one JSON file and never deletes anything.

    Rows are laid out by the run they belong to: a row whose own id IS the
    run's id lives directly in the table folder, every other row lives in
    `<table>/<analyzer_run_id>/`. That layout is what keeps reading cheap when
    nothing is ever thrown away — one run's answer opens one run's folder, not
    every diagnosis ever written.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _row_path(self, table: str, row_id: str, run_id: str = "") -> Path:
        folder = self._root / table
        if run_id and run_id != row_id:
            folder = folder / run_id
        return folder / f"{row_id}.json"

    def save(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        """Write the row, replacing any older copy of it.

        Written to a uniquely named temporary file and renamed into place: a
        reader always sees the whole previous row or the whole new one, never
        half of either, even if the process dies mid-write.
        """
        path = self._row_path(table, row_id, str(data.get(RUN_KEY, "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def get(self, table: str, row_id: str) -> dict[str, Any] | None:
        path = self._row_path(table, row_id)
        if path.is_file():
            return _read(path)
        shared = next((self._root / table).glob(f"*/{row_id}.json"), None)
        return _read(shared) if shared is not None else None

    def list(self, table: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return the rows of `table`, reading only the asked-for run's folder."""
        table_dir = self._root / table
        run_id = str((where or {}).get(RUN_KEY, ""))
        folder = table_dir / run_id if run_id else table_dir
        if not folder.is_dir():
            return []
        paths = sorted(folder.glob("*.json")) if run_id else sorted(table_dir.rglob("*.json"))
        rows = [_read(path) for path in paths]
        if where:
            rows = [row for row in rows if all(row.get(k) == v for k, v in where.items())]
        return rows


__all__ = ["FileRepository"]
