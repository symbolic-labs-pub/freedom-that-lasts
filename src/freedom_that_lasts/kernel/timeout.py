"""
Timeout handling for long-running operations.

Provides context managers and decorators to prevent unbounded operations
and enable graceful degradation.
"""

import signal
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Generator, TypeVar

from freedom_that_lasts.kernel.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class TimeoutError(Exception):
    """Raised when an operation exceeds its timeout."""

    pass


@contextmanager
def timeout_context(seconds: int, operation_name: str = "operation") -> Generator[None, None, None]:
    """
    Context manager that raises TimeoutError if operation exceeds time limit.

    Note: This uses SIGALRM and only works on Unix-like systems.
    For Windows or thread-based timeouts, consider using concurrent.futures.

    Args:
        seconds: Maximum seconds to allow for operation
        operation_name: Name of operation for logging

    Raises:
        TimeoutError: If operation exceeds timeout

    Example:
        with timeout_context(30, "command_execution"):
            # This will raise TimeoutError if it takes > 30 seconds
            result = process_command(cmd)
    """

    def _timeout_handler(signum: int, frame: Any) -> None:
        logger.error(
            "Operation exceeded timeout",
            operation=operation_name,
            timeout_seconds=seconds,
        )
        raise TimeoutError(f"{operation_name} exceeded timeout of {seconds} seconds")

    # Save old handler
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        # Restore old handler and cancel alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def with_timeout(
    seconds: int,
    operation_name: str = "operation",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that applies timeout to a function.

    Args:
        seconds: Maximum seconds to allow for operation
        operation_name: Name of operation for logging

    Returns:
        Decorated function with timeout

    Example:
        @with_timeout(30, "handle_create_law")
        def handle_create_law(cmd):
            # This will raise TimeoutError if it takes > 30 seconds
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with timeout_context(seconds, operation_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# Common Timeout Values (from plan)
# ============================================================================

COMMAND_EXECUTION_TIMEOUT = 30  # seconds
PROJECTION_REBUILD_TIMEOUT = 60  # seconds
TICK_EXECUTION_TIMEOUT = 10  # seconds


@contextmanager
def command_execution_timeout(
    command_type: str,
) -> Generator[None, None, None]:
    """
    Context manager for command execution with 30s timeout.

    Args:
        command_type: Type of command being executed

    Example:
        with command_execution_timeout("CreateLaw"):
            result = handler.handle(cmd)
    """
    with timeout_context(COMMAND_EXECUTION_TIMEOUT, f"command:{command_type}"):
        yield


@contextmanager
def projection_rebuild_timeout() -> Generator[None, None, None]:
    """
    Context manager for projection rebuild with 60s timeout.

    Example:
        with projection_rebuild_timeout():
            projection.rebuild()
    """
    with timeout_context(PROJECTION_REBUILD_TIMEOUT, "projection_rebuild"):
        yield


@contextmanager
def tick_execution_timeout() -> Generator[None, None, None]:
    """
    Context manager for tick execution with 10s timeout.

    Example:
        with tick_execution_timeout():
            tick_engine.execute_tick()
    """
    with timeout_context(TICK_EXECUTION_TIMEOUT, "tick_execution"):
        yield
