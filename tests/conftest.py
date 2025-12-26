"""
Pytest configuration and shared fixtures

Fun fact: The name "conftest" comes from pytest's configuration testing
framework. Files named conftest.py are automatically discovered and their
fixtures are available to all tests in the same directory and subdirectories!
"""

import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.projection_store import SQLiteProjectionStore
from freedom_that_lasts.kernel.time import TestTimeProvider


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Provide a temporary database file that's cleaned up after test"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def event_store(temp_db: Path) -> SQLiteEventStore:
    """Provide a fresh event store for each test"""
    return SQLiteEventStore(temp_db)


@pytest.fixture
def projection_store(temp_db: Path) -> SQLiteProjectionStore:
    """Provide a fresh projection store for each test"""
    return SQLiteProjectionStore(temp_db)


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide a controllable time provider for deterministic tests"""
    return TestTimeProvider()
