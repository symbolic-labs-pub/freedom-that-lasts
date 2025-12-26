"""
Time provider abstraction for deterministic testing

Provides both real-time and controllable test-time implementations,
enabling fully deterministic event replay and testing.

Fun fact: The concept of "now" is surprisingly complex in distributed systems.
This abstraction sidesteps relativity theory by making time injectable!
"""

from datetime import datetime, timezone
from typing import Protocol


class TimeProvider(Protocol):
    """Protocol for time providers - allows deterministic testing"""

    def now(self) -> datetime:
        """Return current UTC datetime"""
        ...


class RealTimeProvider:
    """Production time provider using system clock"""

    def now(self) -> datetime:
        """Return current UTC time from system clock"""
        return datetime.now(timezone.utc)


class TestTimeProvider:
    """
    Controllable time provider for deterministic tests

    Allows tests to freeze time, advance time, and ensure
    reproducible event timestamps.
    """

    def __init__(self, initial_time: datetime | None = None) -> None:
        """
        Initialize with optional fixed time

        Args:
            initial_time: Starting time (defaults to Unix epoch)
        """
        self._current_time = initial_time or datetime(1970, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        """Return current test time"""
        return self._current_time

    def set_time(self, dt: datetime) -> None:
        """Set current time to specific value"""
        self._current_time = dt

    def advance_seconds(self, seconds: int) -> None:
        """Advance time by specified seconds"""
        from datetime import timedelta

        self._current_time += timedelta(seconds=seconds)

    def advance_days(self, days: int) -> None:
        """Advance time by specified days"""
        from datetime import timedelta

        self._current_time += timedelta(days=days)


# Global default time provider
default_time_provider: TimeProvider = RealTimeProvider()
