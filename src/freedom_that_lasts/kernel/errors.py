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


# Budget Module Errors


class BudgetError(FTLError):
    """Base class for budget-specific errors"""

    pass


class FlexStepSizeViolation(InvariantViolation):
    """Raised when budget adjustment exceeds flex class step-size limit"""

    def __init__(
        self, item_id: str, flex_class: str, change_percent: float, max_percent: float
    ) -> None:
        self.item_id = item_id
        self.flex_class = flex_class
        self.change_percent = change_percent
        self.max_percent = max_percent
        super().__init__(
            f"Item {item_id} adjustment {change_percent:.1%} exceeds {flex_class} "
            f"limit {max_percent:.1%} - graduated constraints prevent sudden cuts"
        )


class BudgetBalanceViolation(InvariantViolation):
    """Raised when budget adjustments violate zero-sum constraint"""

    def __init__(self, budget_total: str, new_total: str, variance: str) -> None:
        self.budget_total = budget_total
        self.new_total = new_total
        self.variance = variance
        super().__init__(
            f"Budget balance violated: total allocated {new_total} != budget total "
            f"{budget_total} (variance: {variance}) - strict balancing prevents unauthorized growth"
        )


class ExpenditureExceedsAllocation(InvariantViolation):
    """Raised when expenditure would exceed item allocation"""

    def __init__(
        self, item_id: str, amount: str, allocated: str, spent: str, remaining: str
    ) -> None:
        self.item_id = item_id
        self.amount = amount
        self.allocated = allocated
        self.spent = spent
        self.remaining = remaining
        super().__init__(
            f"Item {item_id} expenditure {amount} exceeds remaining budget {remaining} "
            f"(allocated: {allocated}, spent: {spent})"
        )


class AllocationBelowSpending(InvariantViolation):
    """Raised when allocation adjustment would create overspending"""

    def __init__(self, item_id: str, new_allocation: str, spent_amount: str) -> None:
        self.item_id = item_id
        self.new_allocation = new_allocation
        self.spent_amount = spent_amount
        super().__init__(
            f"Item {item_id} allocation {new_allocation} is below current spending "
            f"{spent_amount} - cannot reduce allocation below spending"
        )


class BudgetNotFound(BudgetError):
    """Raised when budget does not exist"""

    def __init__(self, budget_id: str) -> None:
        self.budget_id = budget_id
        super().__init__(f"Budget {budget_id} not found")


class BudgetItemNotFound(BudgetError):
    """Raised when budget item does not exist"""

    def __init__(self, budget_id: str, item_id: str) -> None:
        self.budget_id = budget_id
        self.item_id = item_id
        super().__init__(f"Item {item_id} not found in budget {budget_id}")


class BudgetNotActive(BudgetError):
    """Raised when operation requires ACTIVE budget but budget has different status"""

    def __init__(self, budget_id: str, current_status: str) -> None:
        self.budget_id = budget_id
        self.current_status = current_status
        super().__init__(
            f"Budget {budget_id} is {current_status}, must be ACTIVE for this operation"
        )


class LawNotFoundForBudget(BudgetError):
    """Raised when law does not exist for budget creation"""

    def __init__(self, law_id: str) -> None:
        self.law_id = law_id
        super().__init__(f"Law {law_id} not found - cannot create budget")
