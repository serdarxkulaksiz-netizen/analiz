"""Repository interface (plan.md A10).

Upper layers only ever speak at the level of "save to this table / read from
this table". Table names come from config; no code hardcodes file paths.
Swapping the backend (SQLite/Oracle) means implementing this interface and
injecting it — upper code does not change.
"""

from abc import ABC, abstractmethod
from typing import Any


class Repository(ABC):
    """Pluggable persistence boundary (Halka 6)."""

    @abstractmethod
    def save(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        """Insert or overwrite the row `row_id` in `table`."""

    @abstractmethod
    def get(self, table: str, row_id: str) -> dict[str, Any] | None:
        """Return the row, or None if it does not exist."""

    @abstractmethod
    def list(self, table: str) -> list[dict[str, Any]]:
        """Return all rows of `table` (empty list if the table is empty/missing)."""

    @abstractmethod
    def exists(self, table: str, row_id: str) -> bool:
        """Return True if the row exists."""
