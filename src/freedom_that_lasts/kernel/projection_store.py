"""
Projection Store - Materialized read models from events

Projections are denormalized views built from the event log.
They enable fast queries without replaying entire event streams.

Fun fact: Projections are like database views, but better - they're
incrementally updated as events arrive and can be completely rebuilt
from the event log at any time!
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel


class ProjectionState(BaseModel):
    """
    State of a projection with position tracking

    The position_event_id tracks the last event that was processed,
    enabling incremental updates and crash recovery.
    """

    name: str
    position_event_id: str | None = None
    state: dict[str, Any]
    updated_at: datetime


class SQLiteProjectionStore:
    """
    SQLite-based projection store

    Stores materialized read models that are built from events.
    Each projection tracks its position in the event log for
    incremental updates.

    Schema:
    - projections table: stores projection name, position, and state
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize projection store with SQLite database

        Args:
            db_path: Path to SQLite database file (can be same as event store)
        """
        self.db_path = Path(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create tables if they don't exist"""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projections (
                    name TEXT PRIMARY KEY,
                    position_event_id TEXT,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def save(
        self,
        name: str,
        state: dict[str, Any],
        position_event_id: str | None = None,
    ) -> None:
        """
        Save or update a projection

        Args:
            name: Projection name (e.g., "law_registry", "delegation_graph")
            state: Projection state (must be JSON-serializable)
            position_event_id: Last processed event ID (for incremental updates)
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projections (name, position_event_id, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    position_event_id = excluded.position_event_id,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
            """,
                (
                    name,
                    position_event_id,
                    json.dumps(state),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def load(self, name: str) -> ProjectionState | None:
        """
        Load a projection by name

        Args:
            name: Projection name

        Returns:
            ProjectionState if exists, None otherwise
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT name, position_event_id, state_json, updated_at FROM projections WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return ProjectionState(
                name=row["name"],
                position_event_id=row["position_event_id"],
                state=json.loads(row["state_json"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def load_state(self, name: str) -> dict[str, Any] | None:
        """
        Load just the state portion of a projection

        Args:
            name: Projection name

        Returns:
            State dict if exists, None otherwise
        """
        projection = self.load(name)
        return projection.state if projection else None

    def delete(self, name: str) -> None:
        """
        Delete a projection (for rebuilding)

        Args:
            name: Projection name
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM projections WHERE name = ?", (name,))
            conn.commit()

    def list_projections(self) -> list[str]:
        """
        List all projection names

        Returns:
            List of projection names
        """
        with self._connect() as conn:
            cursor = conn.execute("SELECT name FROM projections ORDER BY name")
            return [row["name"] for row in cursor.fetchall()]

    def get_position(self, name: str) -> str | None:
        """
        Get the last processed event ID for a projection

        Args:
            name: Projection name

        Returns:
            Last processed event ID, or None if projection doesn't exist
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT position_event_id FROM projections WHERE name = ?", (name,)
            )
            row = cursor.fetchone()
            return row["position_event_id"] if row else None
