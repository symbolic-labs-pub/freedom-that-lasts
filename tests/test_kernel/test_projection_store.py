"""
Tests for projection store

Tests SQLite-based projection persistence for materialized read models.
Projections are incrementally updated from event streams and cached for fast queries.

Fun fact: The concept of "materialized views" dates back to the 1970s in database systems,
but the term "projection" in event sourcing was popularized by Greg Young in the 2000s
during the development of CQRS patterns!
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from freedom_that_lasts.kernel.projection_store import (
    ProjectionState,
    SQLiteProjectionStore,
)


@pytest.fixture
def temp_db():
    """Temporary database for projection store tests"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def store(temp_db):
    """Fresh projection store for each test"""
    return SQLiteProjectionStore(temp_db)


# =============================================================================
# Initialization Tests
# =============================================================================


def test_projection_store_creates_schema(temp_db):
    """Test projection store creates schema on initialization"""
    store = SQLiteProjectionStore(temp_db)

    # Verify database file exists
    assert temp_db.exists()

    # Verify we can query the projections table (schema created)
    with store._connect() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projections'")
        table = cursor.fetchone()
        assert table is not None


def test_projection_store_accepts_string_path(temp_db):
    """Test projection store accepts string path"""
    store = SQLiteProjectionStore(str(temp_db))
    assert store.db_path == temp_db


def test_projection_store_accepts_path_object(temp_db):
    """Test projection store accepts Path object"""
    store = SQLiteProjectionStore(temp_db)
    assert store.db_path == temp_db


# =============================================================================
# Save Tests
# =============================================================================


def test_save_new_projection(store):
    """Test saving a new projection"""
    state = {"count": 5, "items": ["a", "b", "c"]}

    store.save("test_projection", state, position_event_id="evt-123")

    # Verify saved
    loaded = store.load("test_projection")
    assert loaded is not None
    assert loaded.name == "test_projection"
    assert loaded.position_event_id == "evt-123"
    assert loaded.state == state


def test_save_projection_without_position(store):
    """Test saving projection without position_event_id"""
    state = {"status": "active"}

    store.save("test_projection", state)

    loaded = store.load("test_projection")
    assert loaded is not None
    assert loaded.position_event_id is None
    assert loaded.state == state


def test_save_updates_existing_projection(store):
    """Test saving updates existing projection (upsert behavior)"""
    # First save
    store.save("test_projection", {"count": 1}, position_event_id="evt-100")

    # Update
    store.save("test_projection", {"count": 2}, position_event_id="evt-200")

    # Verify updated
    loaded = store.load("test_projection")
    assert loaded.state == {"count": 2}
    assert loaded.position_event_id == "evt-200"


def test_save_updates_timestamp(store):
    """Test save updates the updated_at timestamp"""
    # First save
    store.save("test_projection", {"v": 1})
    first_loaded = store.load("test_projection")
    first_timestamp = first_loaded.updated_at

    # Update after a short delay
    import time
    time.sleep(0.01)

    store.save("test_projection", {"v": 2})
    second_loaded = store.load("test_projection")
    second_timestamp = second_loaded.updated_at

    # Timestamp should be updated
    assert second_timestamp > first_timestamp


def test_save_complex_nested_state(store):
    """Test saving projection with complex nested state"""
    state = {
        "laws": {
            "law-1": {
                "status": "ACTIVE",
                "checkpoints": [30, 90, 180],
                "metadata": {"author": "alice", "version": 1},
            }
        },
        "delegations": [
            {"from": "alice", "to": "bob", "expires_at": "2025-12-31T00:00:00Z"}
        ],
        "stats": {"total": 42, "active": 39, "ratio": 0.928},
    }

    store.save("complex_projection", state, position_event_id="evt-999")

    loaded = store.load("complex_projection")
    assert loaded.state == state


# =============================================================================
# Load Tests
# =============================================================================


def test_load_existing_projection(store):
    """Test loading an existing projection"""
    state = {"data": "test"}
    store.save("my_projection", state, position_event_id="evt-555")

    loaded = store.load("my_projection")

    assert loaded is not None
    assert isinstance(loaded, ProjectionState)
    assert loaded.name == "my_projection"
    assert loaded.position_event_id == "evt-555"
    assert loaded.state == state
    assert isinstance(loaded.updated_at, datetime)


def test_load_nonexistent_projection(store):
    """Test loading projection that doesn't exist returns None"""
    loaded = store.load("nonexistent")
    assert loaded is None


def test_load_state_existing_projection(store):
    """Test load_state returns just the state dict"""
    state = {"key": "value", "number": 42}
    store.save("my_projection", state)

    loaded_state = store.load_state("my_projection")

    assert loaded_state == state
    assert isinstance(loaded_state, dict)


def test_load_state_nonexistent_projection(store):
    """Test load_state returns None for nonexistent projection"""
    loaded_state = store.load_state("nonexistent")
    assert loaded_state is None


# =============================================================================
# Delete Tests
# =============================================================================


def test_delete_existing_projection(store):
    """Test deleting an existing projection"""
    store.save("to_delete", {"data": "test"})

    # Verify exists
    assert store.load("to_delete") is not None

    # Delete
    store.delete("to_delete")

    # Verify deleted
    assert store.load("to_delete") is None


def test_delete_nonexistent_projection(store):
    """Test deleting nonexistent projection doesn't raise error"""
    # Should not raise
    store.delete("nonexistent")


def test_delete_and_recreate_projection(store):
    """Test deleting and recreating projection with same name"""
    store.save("projection", {"version": 1}, position_event_id="evt-100")

    store.delete("projection")

    # Recreate with different data
    store.save("projection", {"version": 2}, position_event_id="evt-200")

    loaded = store.load("projection")
    assert loaded.state == {"version": 2}
    assert loaded.position_event_id == "evt-200"


# =============================================================================
# List Projections Tests
# =============================================================================


def test_list_projections_empty_store(store):
    """Test listing projections in empty store"""
    projections = store.list_projections()
    assert projections == []


def test_list_projections_single_projection(store):
    """Test listing single projection"""
    store.save("projection_a", {"data": 1})

    projections = store.list_projections()
    assert projections == ["projection_a"]


def test_list_projections_multiple_projections(store):
    """Test listing multiple projections in alphabetical order"""
    store.save("law_registry", {"laws": []})
    store.save("delegation_graph", {"edges": []})
    store.save("budget_summary", {"total": 0})

    projections = store.list_projections()

    # Should be alphabetically sorted
    assert projections == ["budget_summary", "delegation_graph", "law_registry"]


def test_list_projections_after_delete(store):
    """Test listing projections after deletion"""
    store.save("projection_a", {"data": 1})
    store.save("projection_b", {"data": 2})
    store.save("projection_c", {"data": 3})

    store.delete("projection_b")

    projections = store.list_projections()
    assert projections == ["projection_a", "projection_c"]


# =============================================================================
# Get Position Tests
# =============================================================================


def test_get_position_existing_projection(store):
    """Test getting position from existing projection"""
    store.save("projection", {"data": 1}, position_event_id="evt-12345")

    position = store.get_position("projection")
    assert position == "evt-12345"


def test_get_position_projection_without_position(store):
    """Test getting position from projection saved without position"""
    store.save("projection", {"data": 1})  # No position_event_id

    position = store.get_position("projection")
    assert position is None


def test_get_position_nonexistent_projection(store):
    """Test getting position from nonexistent projection returns None"""
    position = store.get_position("nonexistent")
    assert position is None


def test_get_position_after_update(store):
    """Test position is updated when projection is saved again"""
    store.save("projection", {"v": 1}, position_event_id="evt-100")

    assert store.get_position("projection") == "evt-100"

    # Update position
    store.save("projection", {"v": 2}, position_event_id="evt-200")

    assert store.get_position("projection") == "evt-200"


# =============================================================================
# Integration Tests
# =============================================================================


def test_projection_lifecycle(store):
    """Test complete projection lifecycle: create, update, query, delete"""
    # Create
    store.save("lifecycle_projection", {"stage": "created"}, position_event_id="evt-1")
    assert "lifecycle_projection" in store.list_projections()

    # Update
    store.save("lifecycle_projection", {"stage": "updated"}, position_event_id="evt-2")
    assert store.get_position("lifecycle_projection") == "evt-2"

    # Query
    state = store.load_state("lifecycle_projection")
    assert state == {"stage": "updated"}

    # Delete
    store.delete("lifecycle_projection")
    assert "lifecycle_projection" not in store.list_projections()


def test_multiple_projections_isolation(store):
    """Test multiple projections don't interfere with each other"""
    store.save("projection_a", {"data": "a"}, position_event_id="evt-a")
    store.save("projection_b", {"data": "b"}, position_event_id="evt-b")
    store.save("projection_c", {"data": "c"}, position_event_id="evt-c")

    # Verify isolation
    assert store.load_state("projection_a") == {"data": "a"}
    assert store.load_state("projection_b") == {"data": "b"}
    assert store.load_state("projection_c") == {"data": "c"}

    assert store.get_position("projection_a") == "evt-a"
    assert store.get_position("projection_b") == "evt-b"
    assert store.get_position("projection_c") == "evt-c"


def test_projection_state_model_serialization():
    """Test ProjectionState model validation and serialization"""
    state = ProjectionState(
        name="test",
        position_event_id="evt-123",
        state={"key": "value"},
        updated_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert state.name == "test"
    assert state.position_event_id == "evt-123"
    assert state.state == {"key": "value"}

    # Verify Pydantic serialization works
    data = state.model_dump()
    assert data["name"] == "test"
    assert data["position_event_id"] == "evt-123"
