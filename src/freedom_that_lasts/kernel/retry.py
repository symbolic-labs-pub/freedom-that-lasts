"""
Retry logic with exponential backoff for transient failures.

Provides decorators and utilities for handling SQLite lock contention
and other temporary failures gracefully.
"""

import sqlite3
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from freedom_that_lasts.kernel.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ============================================================================
# Retry Decorators
# ============================================================================


def retry_on_sqlite_lock(
    max_attempts: int = 3,
    min_wait_ms: int = 100,
    max_wait_ms: int = 1000,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for SQLite lock contention (OperationalError).

    SQLite uses file-based locking and can encounter "database is locked"
    errors under concurrent access. This decorator retries with exponential
    backoff to handle transient locking issues.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait_ms: Minimum wait time in milliseconds (default: 100)
        max_wait_ms: Maximum wait time in milliseconds (default: 1000)

    Returns:
        Decorated function that retries on sqlite3.OperationalError

    Example:
        @retry_on_sqlite_lock()
        def append_events(...):
            # This will retry up to 3 times on database lock errors
            cursor.execute(...)
    """
    return retry(
        retry=retry_if_exception_type(sqlite3.OperationalError),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=min_wait_ms / 1000.0,  # Convert to seconds
            max=max_wait_ms / 1000.0,
        ),
        before_sleep=lambda retry_state: logger.warning(
            "SQLite lock detected, retrying",
            attempt=retry_state.attempt_number,
            exception=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        ),
        reraise=True,
    )


def retry_on_transient_error(
    max_attempts: int = 3,
    min_wait_ms: int = 100,
    max_wait_ms: int = 1000,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Generic retry decorator for transient errors.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait_ms: Minimum wait time in milliseconds (default: 100)
        max_wait_ms: Maximum wait time in milliseconds (default: 1000)
        exceptions: Tuple of exception types to retry on (default: all exceptions)

    Returns:
        Decorated function that retries on specified exceptions

    Example:
        @retry_on_transient_error(exceptions=(ConnectionError, TimeoutError))
        def fetch_data(...):
            # This will retry up to 3 times on connection errors
            response = requests.get(...)
    """
    return retry(
        retry=retry_if_exception_type(exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=min_wait_ms / 1000.0,
            max=max_wait_ms / 1000.0,
        ),
        before_sleep=lambda retry_state: logger.warning(
            "Transient error detected, retrying",
            attempt=retry_state.attempt_number,
            exception=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        ),
        reraise=True,
    )


# ============================================================================
# Projection Rebuild Retry
# ============================================================================


def retry_projection_rebuild(
    max_attempts: int = 3,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator specifically for projection rebuilds.

    Projection rebuilds can fail due to:
    - SQLite lock contention while reading many events
    - Transient I/O errors
    - Out of memory (less common)

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)

    Returns:
        Decorated function that retries projection rebuilds

    Example:
        @retry_projection_rebuild()
        def rebuild_all_projections(...):
            # This will retry up to 3 times on transient errors
            for projection in projections:
                projection.rebuild()
    """
    return retry(
        retry=retry_if_exception_type((sqlite3.OperationalError, IOError, OSError)),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=0.5,  # 500ms min for rebuilds (longer operations)
            max=5.0,  # 5s max
        ),
        before_sleep=lambda retry_state: logger.warning(
            "Projection rebuild failed, retrying",
            attempt=retry_state.attempt_number,
            exception=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        ),
        reraise=True,
    )
