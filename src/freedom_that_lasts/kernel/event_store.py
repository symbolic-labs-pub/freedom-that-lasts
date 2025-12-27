"""
SQLite Event Store - Append-only event log with idempotency

The event store is the source of truth for the entire system. It provides:
- Append-only semantics (events never modified or deleted)
- Idempotency via command_id (same command = same events)
- Optimistic locking via stream versioning
- Deterministic replay capability

Fun fact: The append-only log pattern is one of the oldest database techniques,
dating back to the 1960s IMS database. We're applying time-tested wisdom to governance!
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from freedom_that_lasts.kernel.errors import (
    CommandIdempotencyViolation,
    EventStoreError,
    StreamVersionConflict,
)
from freedom_that_lasts.kernel.events import Event


class SQLiteEventStore:
    """
    SQLite-based event store with append-only semantics

    This implementation uses SQLite with WAL (Write-Ahead Logging) mode
    for crash safety and good concurrent read performance.

    Schema:
    - events table: append-only event log
    - Unique constraints: (stream_id, version), (command_id)
    - Indices: stream_id, event_type, occurred_at for efficient queries
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize event store with SQLite database

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create tables and indices if they don't exist"""
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for safety
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety and performance

            # Create events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    stream_type TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    command_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor_id TEXT,
                    payload_json TEXT NOT NULL,

                    UNIQUE(stream_id, version)
                )
            """)

            # Create indices for efficient queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_stream "
                "ON events(stream_id, version)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type " "ON events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_time " "ON events(occurred_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_command " "ON events(command_id)"
            )

            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for database connections

        Ensures connections are properly closed and transactions
        are committed or rolled back appropriately.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()

    def append(
        self,
        stream_id: str,
        expected_version: int,
        events: list[Event],
    ) -> list[Event]:
        """
        Append events to a stream with optimistic locking

        This is the core write operation. It ensures:
        1. Idempotency: Same command_id never creates duplicate events
        2. Consistency: Stream version must match expected
        3. Atomicity: All events append together or none do

        Args:
            stream_id: Aggregate root identifier
            expected_version: Expected current stream version (for optimistic locking)
            events: Events to append (must have sequential versions)

        Returns:
            The appended events (may be from previous execution if idempotent)

        Raises:
            CommandIdempotencyViolation: If command_id already exists (returns existing events)
            StreamVersionConflict: If stream version doesn't match expected
            EventStoreError: On other database errors
        """
        if not events:
            return []

        # Check idempotency first - if command already processed FOR THIS STREAM, return existing events
        # NOTE: Same command can produce events in multiple streams (e.g., CompleteTender -> TenderCompleted + ReputationUpdated)
        first_command_id = events[0].command_id
        existing_events = self._get_events_by_command_id(first_command_id)
        # Filter to only events in THIS stream
        existing_events_in_stream = [e for e in existing_events if e.stream_id == stream_id]
        if existing_events_in_stream:
            # Command already processed FOR THIS STREAM - this is SUCCESS (idempotency)
            return existing_events_in_stream

        with self._connect() as conn:
            try:
                # Verify stream version matches expected (optimistic locking)
                current_version = self._get_stream_version(conn, stream_id)
                if current_version != expected_version:
                    raise StreamVersionConflict(stream_id, expected_version, current_version)

                # Append all events in a single transaction
                for event in events:
                    conn.execute(
                        """
                        INSERT INTO events (
                            event_id, stream_id, stream_type, version,
                            command_id, event_type, occurred_at, actor_id, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            event.event_id,
                            event.stream_id,
                            event.stream_type,
                            event.version,
                            event.command_id,
                            event.event_type,
                            event.occurred_at.isoformat(),
                            event.actor_id,
                            json.dumps(event.payload),
                        ),
                    )

                conn.commit()
                return events

            except sqlite3.IntegrityError as e:
                conn.rollback()
                error_msg = str(e).lower()

                # Check if it's a command_id uniqueness violation (idempotency)
                if "command_id" in error_msg:
                    # Race condition: command was processed between our check and insert
                    existing = self._get_events_by_command_id(first_command_id)
                    if existing:
                        return existing
                    raise CommandIdempotencyViolation(first_command_id)

                # Check if it's a stream version conflict
                if "stream_id" in error_msg and "version" in error_msg:
                    current = self._get_stream_version(conn, stream_id)
                    raise StreamVersionConflict(stream_id, expected_version, current)

                raise EventStoreError(f"Failed to append events: {e}") from e

            except (CommandIdempotencyViolation, StreamVersionConflict):
                # Re-raise our own exceptions without wrapping
                raise

            except Exception as e:
                conn.rollback()
                raise EventStoreError(f"Unexpected error appending events: {e}") from e

    def load_stream(self, stream_id: str) -> list[Event]:
        """
        Load all events for a stream in version order

        This is used to reconstruct aggregate state by replaying events.

        Args:
            stream_id: Aggregate root identifier

        Returns:
            List of events in version order (empty if stream doesn't exist)
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    event_id, stream_id, stream_type, version,
                    command_id, event_type, occurred_at, actor_id, payload_json
                FROM events
                WHERE stream_id = ?
                ORDER BY version ASC
            """,
                (stream_id,),
            )

            return [self._row_to_event(row) for row in cursor.fetchall()]

    def load_all_events(
        self,
        from_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """
        Load events in chronological order (for projection rebuilding)

        Args:
            from_event_id: Start from this event (exclusive), or None for all events
            limit: Maximum number of events to return, or None for all

        Returns:
            List of events in chronological order
        """
        with self._connect() as conn:
            if from_event_id:
                # Get occurred_at timestamp of from_event_id
                cursor = conn.execute(
                    "SELECT occurred_at FROM events WHERE event_id = ?", (from_event_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return []
                from_time = row[0]

                # Get events after that time
                query = """
                    SELECT
                        event_id, stream_id, stream_type, version,
                        command_id, event_type, occurred_at, actor_id, payload_json
                    FROM events
                    WHERE occurred_at > ?
                    ORDER BY occurred_at ASC, event_id ASC
                """
                params = (from_time,)
            else:
                query = """
                    SELECT
                        event_id, stream_id, stream_type, version,
                        command_id, event_type, occurred_at, actor_id, payload_json
                    FROM events
                    ORDER BY occurred_at ASC, event_id ASC
                """
                params = ()

            if limit:
                query += f" LIMIT {limit}"

            cursor = conn.execute(query, params)
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def query_events(
        self,
        *,
        stream_type: str | None = None,
        event_type: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """
        Query events by various criteria

        Args:
            stream_type: Filter by stream type (e.g., "workspace", "law")
            event_type: Filter by event type (e.g., "LawActivated")
            from_time: Events after this time (inclusive)
            to_time: Events before this time (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of matching events in chronological order
        """
        with self._connect() as conn:
            conditions = []
            params = []

            if stream_type:
                conditions.append("stream_type = ?")
                params.append(stream_type)

            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type)

            if from_time:
                conditions.append("occurred_at >= ?")
                params.append(from_time.isoformat())

            if to_time:
                conditions.append("occurred_at <= ?")
                params.append(to_time.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT
                    event_id, stream_id, stream_type, version,
                    command_id, event_type, occurred_at, actor_id, payload_json
                FROM events
                WHERE {where_clause}
                ORDER BY occurred_at ASC, event_id ASC
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor = conn.execute(query, params)
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_stream_version(self, stream_id: str) -> int:
        """
        Get current version of a stream

        Args:
            stream_id: Aggregate root identifier

        Returns:
            Current stream version (0 if stream doesn't exist)
        """
        with self._connect() as conn:
            return self._get_stream_version(conn, stream_id)

    def _get_stream_version(self, conn: sqlite3.Connection, stream_id: str) -> int:
        """Internal helper to get stream version within a connection"""
        cursor = conn.execute(
            "SELECT MAX(version) FROM events WHERE stream_id = ?",
            (stream_id,),
        )
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def _get_events_by_command_id(self, command_id: str) -> list[Event]:
        """Get events for a command (for idempotency checking)"""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    event_id, stream_id, stream_type, version,
                    command_id, event_type, occurred_at, actor_id, payload_json
                FROM events
                WHERE command_id = ?
                ORDER BY version ASC
            """,
                (command_id,),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        """Convert SQLite row to Event object"""
        return Event(
            event_id=row["event_id"],
            stream_id=row["stream_id"],
            stream_type=row["stream_type"],
            version=row["version"],
            command_id=row["command_id"],
            event_type=row["event_type"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            actor_id=row["actor_id"],
            payload=json.loads(row["payload_json"]),
        )

    def count_events(self) -> int:
        """Get total number of events in store"""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM events")
            return cursor.fetchone()[0]

    def count_streams(self) -> int:
        """Get total number of distinct streams"""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT stream_id) FROM events")
            return cursor.fetchone()[0]
