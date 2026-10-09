"""In-memory repository — rows live only until the answer is collected."""

from copy import deepcopy
from typing import Any

from app.persistence.repository import Repository


class MemoryRepository(Repository):
    """Keeps the newest runs in memory and writes nothing to disk."""

    def __init__(self, max_runs: int = 20, runs_table: str = "runs") -> None:
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}
        self._run_order: list[str] = []
        self._max_runs = max_runs
        self._runs_table = runs_table

    def save(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        """Store the row — unless it belongs to a run that is already gone.

        Only the runs table admits a new id. A late row from an evicted run is
        dropped instead of stored: its run can no longer be read, so keeping the
        row would both waste memory and let a dead run push a live one out.
        """
        analyzer_run_id = str(data.get("analyzer_run_id", ""))
        if table == self._runs_table:
            self._admit(analyzer_run_id)
        elif analyzer_run_id and not self._known(analyzer_run_id):
            return
        self._tables.setdefault(table, {})[row_id] = deepcopy(data)

    def get(self, table: str, row_id: str) -> dict[str, Any] | None:
        row = self._tables.get(table, {}).get(row_id)
        return deepcopy(row) if row is not None else None

    def list(self, table: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = list(self._tables.get(table, {}).values())
        if where:
            rows = [row for row in rows if all(row.get(k) == v for k, v in where.items())]
        return [deepcopy(row) for row in rows]

    def exists(self, table: str, row_id: str) -> bool:
        return row_id in self._tables.get(table, {})

    def _known(self, analyzer_run_id: str) -> bool:
        return self._max_runs <= 0 or analyzer_run_id in self._run_order

    def _admit(self, analyzer_run_id: str) -> None:
        """Register a run and evict the oldest one once the limit is passed."""
        if not analyzer_run_id or self._max_runs <= 0:
            return
        if analyzer_run_id not in self._run_order:
            self._run_order.append(analyzer_run_id)
        while len(self._run_order) > self._max_runs:
            self._forget(self._run_order.pop(0))

    def _forget(self, analyzer_run_id: str) -> None:
        """Drop every row of one run — the run itself and its diagnoses."""
        for rows in self._tables.values():
            for row_id in [
                row_id
                for row_id, row in rows.items()
                if row.get("analyzer_run_id") == analyzer_run_id
            ]:
                del rows[row_id]


__all__ = ["MemoryRepository"]
