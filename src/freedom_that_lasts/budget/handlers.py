"""
Budget Module Handlers - Command→Event transformation with Multi-Gate Enforcement

Handlers are the decision-making layer. They:
1. Load current state (from projections)
2. Validate invariants (MULTI-GATE ENFORCEMENT)
3. Generate events if valid
4. Return events for append to event store

Multi-gate enforcement occurs in handle_adjust_allocation:
- Gate 1: Step-size limits (flex class)
- Gate 2: Budget balance (zero-sum)
- Gate 3: Delegation authority (checked by FTL façade)
- Gate 4: Expenditure limits
"""

from decimal import Decimal

from freedom_that_lasts.budget.commands import (
    ActivateBudget,
    AdjustAllocation,
    ApproveExpenditure,
    CloseBudget,
    CreateBudget,
)
from freedom_that_lasts.budget.events import (
    AllocationAdjusted,
    AllocationAdjustmentSpec,
    BudgetActivated,
    BudgetClosed,
    BudgetCreated,
    ExpenditureApproved,
    ExpenditureRejected,
    ItemCreatedSpec,
)
from freedom_that_lasts.budget.invariants import (
    validate_budget_active,
    validate_budget_balance,
    validate_budget_item_exists,
    validate_expenditure_limit,
    validate_flex_step_size,
    validate_law_exists,
    validate_no_overspending_after_adjustment,
)
from freedom_that_lasts.budget.models import Budget, BudgetItem
from freedom_that_lasts.kernel.errors import BudgetNotFound
from freedom_that_lasts.kernel.events import Event, create_event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider


class BudgetCommandHandlers:
    """
    Command handlers for the budget module

    Handlers convert commands into events, enforcing multi-gate invariants.
    They depend on projections to get current state.
    """

    def __init__(
        self,
        time_provider: TimeProvider,
        safety_policy: SafetyPolicy,
    ) -> None:
        """
        Initialize handlers with dependencies

        Args:
            time_provider: For timestamps (injectable for testing)
            safety_policy: Constitutional parameters
        """
        self.time_provider = time_provider
        self.safety_policy = safety_policy

    def handle_create_budget(
        self,
        command: CreateBudget,
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle CreateBudget command

        Validates:
        - Law exists
        - Items have positive allocations

        Args:
            command: CreateBudget command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws (for validation)

        Returns:
            List of events to append

        Raises:
            LawNotFoundForBudget: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        validate_law_exists(command.law_id, law_registry)

        # Generate budget ID
        budget_id = generate_id()

        # Convert item specs to ItemCreatedSpec with generated IDs
        items_with_ids: list[ItemCreatedSpec] = []
        budget_total = Decimal("0")

        for item_spec in command.items:
            item_id = generate_id()
            items_with_ids.append(
                ItemCreatedSpec(
                    item_id=item_id,
                    name=item_spec.name,
                    allocated_amount=item_spec.allocated_amount,
                    flex_class=item_spec.flex_class,
                    category=item_spec.category,
                )
            )
            budget_total += item_spec.allocated_amount

        # Create event
        event_payload = BudgetCreated(
            budget_id=budget_id,
            law_id=command.law_id,
            fiscal_year=command.fiscal_year,
            items=items_with_ids,
            budget_total=budget_total,
            created_at=now,
            created_by=actor_id,
            metadata=command.metadata,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=budget_id,
            stream_type="budget",
            event_type="BudgetCreated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=1,
        )

        return [event]

    def handle_activate_budget(
        self,
        command: ActivateBudget,
        command_id: str,
        actor_id: str | None,
        budget_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle ActivateBudget command

        Activates a budget (DRAFT → ACTIVE).
        Only ACTIVE budgets can approve expenditures.

        Args:
            command: ActivateBudget command
            command_id: Idempotency key
            actor_id: Who issued the command
            budget_registry: Current budgets

        Returns:
            List of events to append

        Raises:
            BudgetNotFound: If budget doesn't exist
        """
        now = self.time_provider.now()

        # Validate budget exists
        if command.budget_id not in budget_registry:
            raise BudgetNotFound(command.budget_id)

        budget = budget_registry[command.budget_id]
        current_version = budget.get("version", 1)

        # Create event
        event_payload = BudgetActivated(
            budget_id=command.budget_id,
            activated_at=now,
            activated_by=actor_id,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.budget_id,
            stream_type="budget",
            event_type="BudgetActivated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_adjust_allocation(
        self,
        command: AdjustAllocation,
        command_id: str,
        actor_id: str | None,
        budget_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle AdjustAllocation command with MULTI-GATE ENFORCEMENT

        This is the core of budget integrity. ALL four gates must pass:

        Gate 1: Step-size limits (flex class constraints)
        Gate 2: Budget balance (zero-sum, strict)
        Gate 3: Delegation authority (checked by FTL façade, not here)
        Gate 4: No overspending (allocation >= current spending)

        Args:
            command: AdjustAllocation command
            command_id: Idempotency key
            actor_id: Who issued the command
            budget_registry: Current budgets

        Returns:
            List of events to append

        Raises:
            BudgetNotFound: If budget doesn't exist
            FlexStepSizeViolation: If any adjustment exceeds flex class limit (Gate 1)
            BudgetBalanceViolation: If adjustments break zero-sum (Gate 2)
            AllocationBelowSpending: If adjustment creates overspending (Gate 4)
            BudgetItemNotFound: If item doesn't exist
        """
        now = self.time_provider.now()

        # Validate budget exists
        if command.budget_id not in budget_registry:
            raise BudgetNotFound(command.budget_id)

        budget_data = budget_registry[command.budget_id]
        current_version = budget_data.get("version", 1)

        # Reconstruct Budget model from projection data
        budget = Budget(
            budget_id=budget_data["budget_id"],
            law_id=budget_data["law_id"],
            fiscal_year=budget_data["fiscal_year"],
            items={
                item_id: BudgetItem(**item_data)
                for item_id, item_data in budget_data["items"].items()
            },
            budget_total=Decimal(str(budget_data["budget_total"])),
            status=budget_data["status"],
            created_at=budget_data["created_at"],
            activated_at=budget_data.get("activated_at"),
            closed_at=budget_data.get("closed_at"),
            metadata=budget_data.get("metadata", {}),
        )

        # ========== MULTI-GATE ENFORCEMENT ==========

        # GATE 1: Validate step-size limits for each adjustment
        for adj in command.adjustments:
            # Verify item exists
            item = validate_budget_item_exists(budget, adj.item_id)

            # Validate flex class step-size limit
            validate_flex_step_size(item, adj.change_amount, item.flex_class)

        # GATE 2: Validate budget balance (zero-sum constraint)
        adjustments_dict = [
            {"item_id": adj.item_id, "change_amount": adj.change_amount}
            for adj in command.adjustments
        ]
        validate_budget_balance(budget.items, adjustments_dict, budget.budget_total)

        # GATE 4: Validate no overspending after adjustment
        for adj in command.adjustments:
            item = budget.items[adj.item_id]
            new_allocation = item.allocated_amount + adj.change_amount
            validate_no_overspending_after_adjustment(item, new_allocation)

        # GATE 3: Delegation authority - enforced by FTL façade before calling this handler

        # ========== All gates passed - create event ==========

        # Build adjustment specs for event
        adjustment_specs: list[AllocationAdjustmentSpec] = []
        for adj in command.adjustments:
            item = budget.items[adj.item_id]
            old_amount = item.allocated_amount
            new_amount = old_amount + adj.change_amount

            adjustment_specs.append(
                AllocationAdjustmentSpec(
                    item_id=adj.item_id,
                    old_amount=old_amount,
                    new_amount=new_amount,
                    change_amount=adj.change_amount,
                )
            )

        # Create event
        event_payload = AllocationAdjusted(
            budget_id=command.budget_id,
            adjusted_at=now,
            adjustments=adjustment_specs,
            reason=command.reason,
            adjusted_by=actor_id,
            gates_validated=["step_size", "balance", "authority", "no_overspend"],
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.budget_id,
            stream_type="budget",
            event_type="AllocationAdjusted",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_approve_expenditure(
        self,
        command: ApproveExpenditure,
        command_id: str,
        actor_id: str | None,
        budget_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle ApproveExpenditure command with approval/rejection logic

        Unlike other handlers, this can emit EITHER:
        - ExpenditureApproved (if all validations pass)
        - ExpenditureRejected (if any validation fails)

        This creates an audit trail of failed expenditure attempts.

        Validations:
        - Budget exists
        - Budget is ACTIVE
        - Item exists
        - Expenditure <= remaining budget

        Args:
            command: ApproveExpenditure command
            command_id: Idempotency key
            actor_id: Who issued the command
            budget_registry: Current budgets

        Returns:
            List of events to append (either approval or rejection)
        """
        now = self.time_provider.now()

        # Try to validate - catch any failure and emit rejection event
        try:
            # Validate budget exists
            if command.budget_id not in budget_registry:
                raise BudgetNotFound(command.budget_id)

            budget_data = budget_registry[command.budget_id]
            current_version = budget_data.get("version", 1)

            # Reconstruct Budget model from projection data
            budget = Budget(
                budget_id=budget_data["budget_id"],
                law_id=budget_data["law_id"],
                fiscal_year=budget_data["fiscal_year"],
                items={
                    item_id: BudgetItem(**item_data)
                    for item_id, item_data in budget_data["items"].items()
                },
                budget_total=Decimal(str(budget_data["budget_total"])),
                status=budget_data["status"],
                created_at=budget_data["created_at"],
                activated_at=budget_data.get("activated_at"),
                closed_at=budget_data.get("closed_at"),
                metadata=budget_data.get("metadata", {}),
            )

            # Validate budget is ACTIVE
            validate_budget_active(budget)

            # Validate item exists
            item = validate_budget_item_exists(budget, command.item_id)

            # Validate expenditure limit
            validate_expenditure_limit(item, command.amount)

            # ========== All validations passed - APPROVE ==========

            expenditure_id = generate_id()
            remaining_budget = item.remaining_budget() - command.amount

            event_payload = ExpenditureApproved(
                budget_id=command.budget_id,
                item_id=command.item_id,
                expenditure_id=expenditure_id,
                amount=command.amount,
                purpose=command.purpose,
                approved_at=now,
                approved_by=actor_id,
                remaining_budget=remaining_budget,
                metadata=command.metadata,
            ).model_dump(mode="json")

            event = create_event(
                event_id=generate_id(),
                stream_id=command.budget_id,
                stream_type="budget",
                event_type="ExpenditureApproved",
                occurred_at=now,
                command_id=command_id,
                actor_id=actor_id,
                payload=event_payload,
                version=current_version + 1,
            )

            return [event]

        except Exception as e:
            # ========== Validation failed - REJECT ==========

            # Determine which gate failed
            gate_failed = "unknown"
            rejection_reason = str(e)

            if isinstance(e, BudgetNotFound):
                gate_failed = "budget_not_found"
            elif "ACTIVE" in str(e):
                gate_failed = "budget_status"
            elif "not found" in str(e).lower() and "item" in str(e).lower():
                gate_failed = "item_not_found"
            elif "exceeds" in str(e).lower():
                gate_failed = "insufficient_budget"

            # Get version (may not exist if budget not found)
            current_version = 1
            if command.budget_id in budget_registry:
                current_version = budget_registry[command.budget_id].get("version", 1)

            event_payload = ExpenditureRejected(
                budget_id=command.budget_id,
                item_id=command.item_id,
                amount=command.amount,
                purpose=command.purpose,
                rejected_at=now,
                rejection_reason=rejection_reason,
                gate_failed=gate_failed,
            ).model_dump(mode="json")

            event = create_event(
                event_id=generate_id(),
                stream_id=command.budget_id,
                stream_type="budget",
                event_type="ExpenditureRejected",
                occurred_at=now,
                command_id=command_id,
                actor_id=actor_id,
                payload=event_payload,
                version=current_version + 1,
            )

            return [event]

    def handle_close_budget(
        self,
        command: CloseBudget,
        command_id: str,
        actor_id: str | None,
        budget_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle CloseBudget command

        Closes a budget at end of fiscal year.
        Calculates final totals for audit trail.
        After closure, no further expenditures or adjustments allowed.

        Args:
            command: CloseBudget command
            command_id: Idempotency key
            actor_id: Who issued the command
            budget_registry: Current budgets

        Returns:
            List of events to append

        Raises:
            BudgetNotFound: If budget doesn't exist
        """
        now = self.time_provider.now()

        # Validate budget exists
        if command.budget_id not in budget_registry:
            raise BudgetNotFound(command.budget_id)

        budget_data = budget_registry[command.budget_id]
        current_version = budget_data.get("version", 1)

        # Calculate final totals
        final_total_allocated = Decimal("0")
        final_total_spent = Decimal("0")

        for item_data in budget_data["items"].values():
            final_total_allocated += Decimal(str(item_data["allocated_amount"]))
            final_total_spent += Decimal(str(item_data["spent_amount"]))

        final_total_remaining = final_total_allocated - final_total_spent

        # Create event
        event_payload = BudgetClosed(
            budget_id=command.budget_id,
            closed_at=now,
            reason=command.reason,
            final_total_allocated=final_total_allocated,
            final_total_spent=final_total_spent,
            final_total_remaining=final_total_remaining,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.budget_id,
            stream_type="budget",
            event_type="BudgetClosed",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]
