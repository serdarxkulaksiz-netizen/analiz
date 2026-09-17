"""File-based Repository — the DB simulation."""

import json
import os
from pathlib import Path
from typing import Any

from app.persistence.repository import Repository


class FileRepository(Repository):
    """Stores rows as JSON files under a root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _table_dir(self, table: str) -> Path:
        return self._root / table

    def _row_path(self, table: str, row_id: str) -> Path:
        return self._table_dir(table) / f"{row_id}.json"

    def save(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        table_dir = self._table_dir(table)
        table_dir.mkdir(parents=True, exist_ok=True)
        path = self._row_path(table, row_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def get(self, table: str, row_id: str) -> dict[str, Any] | None:
        path = self._row_path(table, row_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, table: str) -> list[dict[str, Any]]:
        table_dir = self._table_dir(table)
        if not table_dir.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(table_dir.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        return rows

    def exists(self, table: str, row_id: str) -> bool:
        return self._row_path(table, row_id).is_file()
