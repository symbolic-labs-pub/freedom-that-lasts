"""
In-process Command/Event Bus

Simple synchronous bus for command handling and event publishing.
Provides registration, dispatch, and pub/sub mechanics in-process.

Fun fact: This is a "mediator" pattern - it decouples command senders
from handlers, making the system modular and testable. In production,
this could be replaced with Kafka, NATS, or RabbitMQ without changing
domain code!
"""

from collections import defaultdict
from typing import Callable

from freedom_that_lasts.kernel.commands import Command
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.logging import LogOperation, get_logger
from freedom_that_lasts.kernel.metrics import commands_processed_total

logger = get_logger(__name__)


# Type aliases for clarity
CommandHandler = Callable[[Command], list[Event]]
EventHandler = Callable[[Event], None]


class InProcessBus:
    """
    Simple synchronous in-process bus

    Provides command routing and event publishing within a single process.
    Suitable for v0.1 (local development, testing, single-instance deployments).

    For distributed scenarios, replace with message queue adapter while
    keeping the same interface.
    """

    def __init__(self) -> None:
        """Initialize empty bus with no registered handlers"""
        self._command_handlers: dict[str, CommandHandler] = {}
        self._event_handlers: defaultdict[str, list[EventHandler]] = defaultdict(list)
        logger.info("InProcessBus initialized")

    def register_command_handler(
        self, command_type: str, handler: CommandHandler
    ) -> None:
        """
        Register a command handler

        Args:
            command_type: Type of command to handle (e.g., "CreateWorkspace")
            handler: Function that processes command and returns events

        Raises:
            ValueError: If handler already registered for this command type
        """
        if command_type in self._command_handlers:
            logger.error(
                "Command handler registration failed - already exists",
                command_type=command_type,
            )
            raise ValueError(
                f"Command handler already registered for {command_type}. "
                "Each command type can have only one handler (single responsibility)."
            )
        self._command_handlers[command_type] = handler
        logger.debug("Command handler registered", command_type=command_type)

    def register_event_handler(self, event_type: str, handler: EventHandler) -> None:
        """
        Register an event handler (can have multiple per event type)

        Args:
            event_type: Type of event to handle (e.g., "LawActivated")
            handler: Function that processes event (typically updates a projection)

        Note: Multiple handlers can subscribe to the same event type.
        This enables multiple projections to be updated from the same event.
        """
        self._event_handlers[event_type].append(handler)
        handler_count = len(self._event_handlers[event_type])
        logger.debug(
            "Event handler registered",
            event_type=event_type,
            total_handlers=handler_count,
        )

    def dispatch_command(self, command: Command) -> list[Event]:
        """
        Dispatch a command to its handler

        Args:
            command: Command to dispatch

        Returns:
            Events emitted by the command handler

        Raises:
            ValueError: If no handler registered for command type
        """
        handler = self._command_handlers.get(command.command_type)
        if not handler:
            logger.error(
                "No handler registered for command type",
                command_type=command.command_type,
                command_id=command.command_id,
                available_handlers=list(self._command_handlers.keys()),
            )
            raise ValueError(
                f"No handler registered for command type '{command.command_type}'. "
                f"Available handlers: {list(self._command_handlers.keys())}"
            )

        # Log and track metrics for command dispatch
        with LogOperation(
            logger,
            "dispatch_command",
            command_type=command.command_type,
            command_id=command.command_id,
            actor_id=getattr(command, "actor_id", None),
        ):
            try:
                events = handler(command)
                # Track successful command execution
                commands_processed_total.labels(
                    command_type=command.command_type,
                    status="success",
                ).inc()
                logger.info(
                    "Command processed successfully",
                    command_type=command.command_type,
                    events_emitted=len(events),
                )
                return events
            except Exception as e:
                # Track failed command execution
                commands_processed_total.labels(
                    command_type=command.command_type,
                    status="failure",
                ).inc()
                logger.error(
                    "Command processing failed",
                    command_type=command.command_type,
                    command_id=command.command_id,
                    error=str(e),
                    exc_info=True,
                )
                raise

    def publish_event(self, event: Event) -> None:
        """
        Publish an event to all registered handlers

        Args:
            event: Event to publish

        Note: Handlers are called synchronously in registration order.
        If a handler fails, it doesn't affect other handlers (we catch and log).
        """
        handlers = self._event_handlers.get(event.event_type, [])

        if not handlers:
            logger.debug(
                "No handlers registered for event type",
                event_type=event.event_type,
                event_id=event.event_id,
            )
            return

        logger.debug(
            "Publishing event",
            event_type=event.event_type,
            event_id=event.event_id,
            stream_id=event.stream_id,
            handler_count=len(handlers),
        )

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Use structured logging instead of print
                logger.error(
                    "Event handler failed",
                    event_type=event.event_type,
                    event_id=event.event_id,
                    stream_id=event.stream_id,
                    error=str(e),
                    exc_info=True,
                )
                # Continue with other handlers - one failure shouldn't break everything

    def publish_events(self, events: list[Event]) -> None:
        """
        Publish multiple events (convenience method)

        Args:
            events: List of events to publish
        """
        if events:
            logger.debug(
                "Publishing multiple events",
                event_count=len(events),
                event_types=[e.event_type for e in events],
            )
        for event in events:
            self.publish_event(event)

    def get_command_types(self) -> list[str]:
        """
        Get list of registered command types

        Returns:
            List of command types that have handlers
        """
        return list(self._command_handlers.keys())

    def get_event_types(self) -> list[str]:
        """
        Get list of event types that have subscribers

        Returns:
            List of event types with at least one handler
        """
        return list(self._event_handlers.keys())

    def clear(self) -> None:
        """
        Clear all registered handlers (useful for testing)

        Removes all command and event handlers, resetting bus to empty state.
        """
        command_count = len(self._command_handlers)
        event_count = len(self._event_handlers)
        self._command_handlers.clear()
        self._event_handlers.clear()
        logger.info(
            "Bus cleared",
            command_handlers_removed=command_count,
            event_handlers_removed=event_count,
        )
