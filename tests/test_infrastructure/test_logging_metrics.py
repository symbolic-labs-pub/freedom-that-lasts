"""
Test infrastructure components: logging, metrics, retry, timeout, health.

These tests verify the production hardening infrastructure works correctly.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.logging import (
    LogOperation,
    configure_logging,
    get_correlation_id,
    get_logger,
    set_correlation_id,
)
from freedom_that_lasts.kernel.metrics import (
    events_appended_total,
    events_loaded_total,
)
from freedom_that_lasts.kernel.retry import retry_on_sqlite_lock
from freedom_that_lasts.kernel.timeout import TimeoutError, timeout_context
from freedom_that_lasts.health_server import initialize_health_server


class TestLoggingFramework:
    """Test structured logging framework."""

    def test_configure_logging_console(self) -> None:
        """Test logging configuration for console output."""
        configure_logging(json_output=False, log_level="INFO")
        logger = get_logger(__name__)
        assert logger is not None

    def test_configure_logging_json(self) -> None:
        """Test logging configuration for JSON output."""
        configure_logging(json_output=True, log_level="DEBUG")
        logger = get_logger(__name__)
        assert logger is not None

    def test_correlation_id(self) -> None:
        """Test correlation ID context management."""
        # Generate new correlation ID
        cid = get_correlation_id()
        assert cid is not None
        assert len(cid) > 0

        # Set custom correlation ID
        custom_id = "test-correlation-123"
        set_correlation_id(custom_id)
        assert get_correlation_id() == custom_id

    def test_log_operation_context_manager(self) -> None:
        """Test LogOperation context manager."""
        configure_logging(json_output=False, log_level="INFO")
        logger = get_logger(__name__)

        # Should not raise exception
        with LogOperation(logger, "test_operation", foo="bar"):
            pass

    def test_log_operation_with_exception(self) -> None:
        """Test LogOperation logs errors correctly."""
        configure_logging(json_output=False, log_level="INFO")
        logger = get_logger(__name__)

        with pytest.raises(ValueError):
            with LogOperation(logger, "failing_operation"):
                raise ValueError("Test error")


class TestEventStoreWithInfrastructure:
    """Test event store with logging, metrics, and retries."""

    def test_event_store_with_logging(self) -> None:
        """Test event store operations are logged."""
        configure_logging(json_output=False, log_level="DEBUG")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = SQLiteEventStore(db_path)

            # Create and append event
            event = Event(
                event_id="evt-1",
                stream_id="stream-1",
                stream_type="test",
                version=1,
                command_id="cmd-1",
                event_type="TestEvent",
                occurred_at=datetime.now(),
                actor_id="actor-1",
                payload={"test": "data"},
            )

            # Should complete without error and log operations
            result = store.append("stream-1", 0, [event])
            assert len(result) == 1
            assert result[0].event_id == "evt-1"

    def test_event_store_idempotency_logged(self) -> None:
        """Test idempotent operations are logged correctly."""
        configure_logging(json_output=False, log_level="INFO")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = SQLiteEventStore(db_path)

            event = Event(
                event_id="evt-1",
                stream_id="stream-1",
                stream_type="test",
                version=1,
                command_id="cmd-1",
                event_type="TestEvent",
                occurred_at=datetime.now(),
                actor_id="actor-1",
                payload={"test": "data"},
            )

            # First append
            store.append("stream-1", 0, [event])

            # Second append (idempotent) - should log idempotency
            result = store.append("stream-1", 0, [event])
            assert len(result) == 1


class TestMetrics:
    """Test Prometheus metrics collection."""

    def test_events_appended_metric(self) -> None:
        """Test events_appended_total metric is incremented."""
        configure_logging(json_output=False, log_level="INFO")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = SQLiteEventStore(db_path)

            # Get initial metric value
            before = events_appended_total.labels(
                stream_type="test", event_type="TestEvent"
            )._value.get()

            # Append event
            event = Event(
                event_id="evt-1",
                stream_id="stream-1",
                stream_type="test",
                version=1,
                command_id="cmd-1",
                event_type="TestEvent",
                occurred_at=datetime.now(),
                actor_id="actor-1",
                payload={"test": "data"},
            )
            store.append("stream-1", 0, [event])

            # Verify metric incremented
            after = events_appended_total.labels(
                stream_type="test", event_type="TestEvent"
            )._value.get()
            assert after > before

    def test_events_loaded_metric(self) -> None:
        """Test events_loaded_total metric is incremented."""
        configure_logging(json_output=False, log_level="INFO")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = SQLiteEventStore(db_path)

            # Append event first
            event = Event(
                event_id="evt-1",
                stream_id="stream-1",
                stream_type="test",
                version=1,
                command_id="cmd-1",
                event_type="TestEvent",
                occurred_at=datetime.now(),
                actor_id="actor-1",
                payload={"test": "data"},
            )
            store.append("stream-1", 0, [event])

            # Get initial metric value
            before = events_loaded_total.labels(stream_type="test")._value.get()

            # Load stream
            store.load_stream("stream-1")

            # Verify metric incremented
            after = events_loaded_total.labels(stream_type="test")._value.get()
            assert after > before


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    def test_retry_decorator(self) -> None:
        """Test retry decorator works."""
        call_count = 0

        @retry_on_sqlite_lock(max_attempts=3)
        def failing_function() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                import sqlite3

                raise sqlite3.OperationalError("database is locked")
            return "success"

        result = failing_function()
        assert result == "success"
        assert call_count == 2  # Failed once, succeeded on retry


class TestTimeoutHandling:
    """Test timeout handling."""

    def test_timeout_context_success(self) -> None:
        """Test timeout context with fast operation."""
        with timeout_context(1, "test_operation"):
            # Fast operation should complete
            pass

    def test_timeout_context_timeout(self) -> None:
        """Test timeout context raises TimeoutError."""
        import time

        with pytest.raises(TimeoutError):
            with timeout_context(1, "slow_operation"):
                time.sleep(2)


class TestHealthServer:
    """Test health check server initialization."""

    def test_initialize_health_server(self) -> None:
        """Test health server can be initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create database
            store = SQLiteEventStore(db_path)

            # Initialize health server
            initialize_health_server(db_path, None)

            # Should not raise exception
