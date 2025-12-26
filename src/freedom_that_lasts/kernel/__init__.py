"""
Kernel - Core event sourcing infrastructure

The kernel provides the foundational event sourcing machinery that all domain
modules build upon. It enforces determinism, idempotency, and append-only semantics.

Fun fact: Event sourcing was inspired by accountants - they never erase ledger
entries, they add correcting entries. This system applies that wisdom to governance.
"""

from freedom_that_lasts.kernel.commands import Command
from freedom_that_lasts.kernel.errors import (
    CommandIdempotencyViolation,
    EventStoreError,
    FTLError,
    InvariantViolation,
    StreamVersionConflict,
)
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import IdFactory, generate_id
from freedom_that_lasts.kernel.time import RealTimeProvider, TestTimeProvider, TimeProvider

__all__ = [
    # IDs
    "IdFactory",
    "generate_id",
    # Time
    "TimeProvider",
    "RealTimeProvider",
    "TestTimeProvider",
    # Events & Commands
    "Event",
    "Command",
    # Errors
    "FTLError",
    "EventStoreError",
    "CommandIdempotencyViolation",
    "StreamVersionConflict",
    "InvariantViolation",
]
