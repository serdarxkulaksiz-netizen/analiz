"""In-memory repository — rows live only until the answer is collected."""

from copy import deepcopy
from typing import Any

from app.persistence.repository import Repository


class MemoryRepository(Repository):
    """Keeps the newest runs in memory and writes nothing to disk."""

    def __init__(self, max_runs: int = 20) -> None:
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}
        self._run_order: list[str] = []
        self._max_runs = max_runs

    def save(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        self._tables.setdefault(table, {})[row_id] = deepcopy(data)
        self._remember(str(data.get("analyzer_run_id", "")))

    def get(self, table: str, row_id: str) -> dict[str, Any] | None:
        row = self._tables.get(table, {}).get(row_id)
        return deepcopy(row) if row is not None else None

    def list(self, table: str) -> list[dict[str, Any]]:
        return [deepcopy(row) for row in self._tables.get(table, {}).values()]

    def exists(self, table: str, row_id: str) -> bool:
        return row_id in self._tables.get(table, {})

    def _remember(self, analyzer_run_id: str) -> None:
        """Track run order and drop the oldest run once the limit is passed.

        Every row of a run carries its `analyzer_run_id`, so one id is enough to
        evict a run together with its diagnoses — a run whose rows outlived it
        would be invisible and unreachable, taking memory for nothing.
        """
        if not analyzer_run_id or self._max_runs <= 0:
            return
        if analyzer_run_id not in self._run_order:
            self._run_order.append(analyzer_run_id)
        while len(self._run_order) > self._max_runs:
            self._forget(self._run_order.pop(0))

    def _forget(self, analyzer_run_id: str) -> None:
        for rows in self._tables.values():
            for row_id in [
                row_id
                for row_id, row in rows.items()
                if row.get("analyzer_run_id") == analyzer_run_id
            ]:
                del rows[row_id]


__all__ = ["MemoryRepository"]
