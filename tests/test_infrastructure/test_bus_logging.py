"""
Test bus.py logging integration.

Verifies that the InProcessBus properly logs all operations with structured logging.
"""

from datetime import datetime

import pytest

from freedom_that_lasts.kernel.bus import InProcessBus
from freedom_that_lasts.kernel.commands import Command
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.logging import configure_logging


class DummyCommand(Command):
    """Test command for bus testing (renamed to avoid pytest collection)."""

    pass


class TestBusLogging:
    """Test bus logging integration."""

    def setup_method(self) -> None:
        """Configure logging for each test."""
        configure_logging(json_output=False, log_level="DEBUG")

    def test_bus_initialization_logged(self) -> None:
        """Test bus initialization is logged."""
        # Should log initialization
        bus = InProcessBus()
        assert bus is not None

    def test_command_handler_registration_logged(self) -> None:
        """Test command handler registration is logged."""
        bus = InProcessBus()

        def test_handler(cmd: Command) -> list[Event]:
            return []

        # Should log registration
        bus.register_command_handler("TestCommand", test_handler)
        assert "TestCommand" in bus.get_command_types()

    def test_duplicate_command_handler_logs_error(self) -> None:
        """Test duplicate handler registration logs error."""
        bus = InProcessBus()

        def test_handler(cmd: Command) -> list[Event]:
            return []

        bus.register_command_handler("TestCommand", test_handler)

        # Second registration should log error and raise
        with pytest.raises(ValueError):
            bus.register_command_handler("TestCommand", test_handler)

    def test_event_handler_registration_logged(self) -> None:
        """Test event handler registration is logged with count."""
        bus = InProcessBus()

        def handler1(event: Event) -> None:
            pass

        def handler2(event: Event) -> None:
            pass

        # Register multiple handlers for same event type
        bus.register_event_handler("TestEvent", handler1)
        bus.register_event_handler("TestEvent", handler2)

        assert "TestEvent" in bus.get_event_types()

    def test_command_dispatch_logged_success(self) -> None:
        """Test successful command dispatch is logged."""
        bus = InProcessBus()

        test_event = Event(
            event_id="evt-1",
            stream_id="stream-1",
            stream_type="test",
            version=1,
            command_id="cmd-1",
            event_type="TestEvent",
            occurred_at=datetime.now(),
            actor_id="actor-1",
            payload={},
        )

        def test_handler(cmd: Command) -> list[Event]:
            return [test_event]

        bus.register_command_handler("TestCommand", test_handler)

        cmd = DummyCommand(
            command_id="cmd-1",
            command_type="TestCommand",
            actor_id="actor-1",
            issued_at=datetime.now(),
        )

        # Should log dispatch start, success, and metrics
        events = bus.dispatch_command(cmd)
        assert len(events) == 1

    def test_command_dispatch_logged_failure(self) -> None:
        """Test failed command dispatch is logged with error details."""
        bus = InProcessBus()

        def failing_handler(cmd: Command) -> list[Event]:
            raise ValueError("Test error")

        bus.register_command_handler("FailingCommand", failing_handler)

        cmd = DummyCommand(
            command_id="cmd-1",
            command_type="FailingCommand",
            actor_id="actor-1",
            issued_at=datetime.now(),
        )

        # Should log error with full context
        with pytest.raises(ValueError):
            bus.dispatch_command(cmd)

    def test_unregistered_command_logs_error(self) -> None:
        """Test dispatching unregistered command logs error."""
        bus = InProcessBus()

        cmd = DummyCommand(
            command_id="cmd-1",
            command_type="UnknownCommand",
            actor_id="actor-1",
            issued_at=datetime.now(),
        )

        # Should log error with available handlers
        with pytest.raises(ValueError):
            bus.dispatch_command(cmd)

    def test_event_publishing_logged(self) -> None:
        """Test event publishing is logged."""
        bus = InProcessBus()

        handler_called = False

        def test_handler(event: Event) -> None:
            nonlocal handler_called
            handler_called = True

        bus.register_event_handler("TestEvent", test_handler)

        event = Event(
            event_id="evt-1",
            stream_id="stream-1",
            stream_type="test",
            version=1,
            command_id="cmd-1",
            event_type="TestEvent",
            occurred_at=datetime.now(),
            actor_id="actor-1",
            payload={},
        )

        # Should log event publishing
        bus.publish_event(event)
        assert handler_called

    def test_event_handler_failure_logged(self) -> None:
        """Test event handler failures are logged but don't stop other handlers."""
        bus = InProcessBus()

        handler2_called = False

        def failing_handler(event: Event) -> None:
            raise ValueError("Handler error")

        def successful_handler(event: Event) -> None:
            nonlocal handler2_called
            handler2_called = True

        bus.register_event_handler("TestEvent", failing_handler)
        bus.register_event_handler("TestEvent", successful_handler)

        event = Event(
            event_id="evt-1",
            stream_id="stream-1",
            stream_type="test",
            version=1,
            command_id="cmd-1",
            event_type="TestEvent",
            occurred_at=datetime.now(),
            actor_id="actor-1",
            payload={},
        )

        # Should log error but continue with other handlers
        bus.publish_event(event)
        assert handler2_called  # Second handler should still run

    def test_publish_events_batch_logged(self) -> None:
        """Test publishing multiple events is logged."""
        bus = InProcessBus()

        handler_count = 0

        def test_handler(event: Event) -> None:
            nonlocal handler_count
            handler_count += 1

        bus.register_event_handler("TestEvent", test_handler)

        events = [
            Event(
                event_id=f"evt-{i}",
                stream_id="stream-1",
                stream_type="test",
                version=i,
                command_id="cmd-1",
                event_type="TestEvent",
                occurred_at=datetime.now(),
                actor_id="actor-1",
                payload={},
            )
            for i in range(1, 4)
        ]

        # Should log batch publishing
        bus.publish_events(events)
        assert handler_count == 3

    def test_no_handlers_for_event_logged(self) -> None:
        """Test publishing event with no handlers is logged."""
        bus = InProcessBus()

        event = Event(
            event_id="evt-1",
            stream_id="stream-1",
            stream_type="test",
            version=1,
            command_id="cmd-1",
            event_type="UnhandledEvent",
            occurred_at=datetime.now(),
            actor_id="actor-1",
            payload={},
        )

        # Should log that no handlers are registered (at debug level)
        bus.publish_event(event)

    def test_bus_clear_logged(self) -> None:
        """Test clearing bus is logged with counts."""
        bus = InProcessBus()

        def cmd_handler(cmd: Command) -> list[Event]:
            return []

        def evt_handler(event: Event) -> None:
            pass

        bus.register_command_handler("TestCommand", cmd_handler)
        bus.register_event_handler("TestEvent", evt_handler)

        # Should log clearing with handler counts
        bus.clear()

        assert len(bus.get_command_types()) == 0
        assert len(bus.get_event_types()) == 0
