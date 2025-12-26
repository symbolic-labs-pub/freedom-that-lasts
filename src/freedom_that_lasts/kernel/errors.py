"""
Custom exceptions for Freedom That Lasts

Well-defined error hierarchy enables precise error handling and
clear error messages for developers and operators.

Fun fact: The first computer bug was an actual moth found in a relay
of the Harvard Mark II computer in 1947. We're debugging governance!
"""


class FTLError(Exception):
    """Base exception for all Freedom That Lasts errors"""

    pass


class EventStoreError(FTLError):
    """Base class for event store errors"""

    pass


class CommandIdempotencyViolation(EventStoreError):
    """
    Raised when attempting to execute a command with duplicate command_id

    This is actually SUCCESS - idempotency means the command was already
    processed, so we return the original events without re-executing.
    """

    def __init__(self, command_id: str, message: str = "") -> None:
        self.command_id = command_id
        super().__init__(
            message or f"Command {command_id} already processed (idempotency preserved)"
        )


class StreamVersionConflict(EventStoreError):
    """
    Raised when stream version doesn't match expected (optimistic locking)

    Indicates concurrent modification - caller should reload and retry.
    """

    def __init__(
        self, stream_id: str, expected_version: int, actual_version: int
    ) -> None:
        self.stream_id = stream_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Stream {stream_id} version mismatch: "
            f"expected {expected_version}, got {actual_version}"
        )


class InvariantViolation(FTLError):
    """
    Raised when domain invariant would be violated

    Invariants are the constitutional constraints - they MUST hold.
    Examples: acyclic delegation graph, TTL bounds, checkpoint schedules.
    """

    pass


class DelegationCycleDetected(InvariantViolation):
    """Raised when delegation would create a cycle in the DAG"""

    def __init__(self, from_actor: str, to_actor: str) -> None:
        self.from_actor = from_actor
        self.to_actor = to_actor
        super().__init__(
            f"Delegation from {from_actor} to {to_actor} would create a cycle - "
            "delegation graph must remain acyclic to prevent power loops"
        )


class TTLExceedsMaximum(InvariantViolation):
    """Raised when delegation TTL exceeds safety policy maximum"""

    def __init__(self, ttl_days: int, max_ttl_days: int) -> None:
        self.ttl_days = ttl_days
        self.max_ttl_days = max_ttl_days
        super().__init__(
            f"Delegation TTL {ttl_days} days exceeds maximum {max_ttl_days} days - "
            "this safeguard prevents permanent power accumulation"
        )


class InvalidCheckpointSchedule(InvariantViolation):
    """Raised when law checkpoint schedule violates minimum requirements"""

    def __init__(self, provided: list[int], minimum: list[int]) -> None:
        self.provided = provided
        self.minimum = minimum
        super().__init__(
            f"Checkpoint schedule {provided} does not meet minimum requirements {minimum} - "
            "mandatory review prevents silent drift into irreversibility"
        )


class WorkspaceNotFound(FTLError):
    """Raised when workspace does not exist"""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace {workspace_id} not found")


class LawNotFound(FTLError):
    """Raised when law does not exist"""

    def __init__(self, law_id: str) -> None:
        self.law_id = law_id
        super().__init__(f"Law {law_id} not found")


class DelegationNotFound(FTLError):
    """Raised when delegation does not exist"""

    def __init__(self, delegation_id: str) -> None:
        self.delegation_id = delegation_id
        super().__init__(f"Delegation {delegation_id} not found")
