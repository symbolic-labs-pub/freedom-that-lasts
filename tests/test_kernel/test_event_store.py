"""
Tests for SQLite Event Store

Verifies core event sourcing properties:
- Append-only semantics
- Idempotency via command_id
- Optimistic locking via stream versioning
- Query capabilities

Fun fact: Event sourcing tests are like archaeology - we're verifying
that the historical record is complete, immutable, and replayable!
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.kernel.errors import CommandIdempotencyViolation, StreamVersionConflict
from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id


def test_append_and_load_single_event(event_store: SQLiteEventStore) -> None:
    """Test appending and loading a single event"""
    # Create an event
    event = Event(
        event_id=generate_id(),
        stream_id="test-stream-1",
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        actor_id="test-actor",
        command_id=generate_id(),
        payload={"message": "Hello, World!"},
        version=1,
    )

    # Append to store
    appended = event_store.append("test-stream-1", 0, [event])
    assert len(appended) == 1
    assert appended[0].event_id == event.event_id

    # Load back
    loaded = event_store.load_stream("test-stream-1")
    assert len(loaded) == 1
    assert loaded[0].event_id == event.event_id
    assert loaded[0].payload == {"message": "Hello, World!"}


def test_stream_versioning(event_store: SQLiteEventStore) -> None:
    """Test that stream versioning works correctly"""
    stream_id = "test-stream-2"

    # Append first event (version 1)
    event1 = Event(
        event_id=generate_id(),
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=generate_id(),
        payload={"sequence": 1},
        version=1,
    )
    event_store.append(stream_id, 0, [event1])

    # Verify stream version is now 1
    assert event_store.get_stream_version(stream_id) == 1

    # Append second event (version 2)
    event2 = Event(
        event_id=generate_id(),
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=generate_id(),
        payload={"sequence": 2},
        version=2,
    )
    event_store.append(stream_id, 1, [event2])

    # Verify stream version is now 2
    assert event_store.get_stream_version(stream_id) == 2

    # Load all events
    events = event_store.load_stream(stream_id)
    assert len(events) == 2
    assert events[0].version == 1
    assert events[1].version == 2


def test_optimistic_locking_conflict(event_store: SQLiteEventStore) -> None:
    """Test that concurrent modifications are detected"""
    stream_id = "test-stream-3"

    # Append first event
    event1 = Event(
        event_id=generate_id(),
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=generate_id(),
        payload={},
        version=1,
    )
    event_store.append(stream_id, 0, [event1])

    # Try to append with wrong expected version (simulating concurrent modification)
    event2 = Event(
        event_id=generate_id(),
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=generate_id(),
        payload={},
        version=2,
    )

    with pytest.raises(StreamVersionConflict) as exc_info:
        event_store.append(stream_id, 0, [event2])  # Wrong: should be version 1

    assert exc_info.value.expected_version == 0
    assert exc_info.value.actual_version == 1


def test_command_idempotency(event_store: SQLiteEventStore) -> None:
    """Test that same command_id doesn't create duplicate events"""
    stream_id = "test-stream-4"
    command_id = generate_id()

    # Append event first time
    event1 = Event(
        event_id=generate_id(),
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=command_id,
        payload={"attempt": 1},
        version=1,
    )
    result1 = event_store.append(stream_id, 0, [event1])
    assert len(result1) == 1

    # Try to append same command_id again (different event_id)
    event2 = Event(
        event_id=generate_id(),  # Different event_id
        stream_id=stream_id,
        stream_type="test",
        event_type="TestEvent",
        occurred_at=datetime.now(timezone.utc),
        command_id=command_id,  # Same command_id
        payload={"attempt": 2},
        version=2,
    )

    # Should return original events (idempotency)
    result2 = event_store.append(stream_id, 1, [event2])
    assert len(result2) == 1
    assert result2[0].event_id == event1.event_id  # Same event returned
    assert result2[0].payload["attempt"] == 1  # Original payload

    # Verify stream still only has one event
    events = event_store.load_stream(stream_id)
    assert len(events) == 1


def test_query_by_event_type(event_store: SQLiteEventStore) -> None:
    """Test querying events by type"""
    # Create events of different types
    for i in range(3):
        event = Event(
            event_id=generate_id(),
            stream_id=f"stream-{i}",
            stream_type="test",
            event_type="TypeA" if i % 2 == 0 else "TypeB",
            occurred_at=datetime.now(timezone.utc),
            command_id=generate_id(),
            payload={},
            version=1,
        )
        event_store.append(f"stream-{i}", 0, [event])

    # Query for TypeA events
    type_a_events = event_store.query_events(event_type="TypeA")
    assert len(type_a_events) == 2

    # Query for TypeB events
    type_b_events = event_store.query_events(event_type="TypeB")
    assert len(type_b_events) == 1


def test_count_operations(event_store: SQLiteEventStore) -> None:
    """Test count operations"""
    # Initially empty
    assert event_store.count_events() == 0
    assert event_store.count_streams() == 0

    # Add events to two different streams
    for stream_num in range(2):
        for version in range(1, 4):
            event = Event(
                event_id=generate_id(),
                stream_id=f"stream-{stream_num}",
                stream_type="test",
                event_type="TestEvent",
                occurred_at=datetime.now(timezone.utc),
                command_id=generate_id(),
                payload={},
                version=version,
            )
            event_store.append(f"stream-{stream_num}", version - 1, [event])

    # Check counts
    assert event_store.count_events() == 6  # 2 streams × 3 events
    assert event_store.count_streams() == 2
