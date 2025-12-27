"""
Budget Module Invariants - Multi-Gate Enforcement

These pure functions enforce the constitutional constraints of the budget system.
They implement the four gates of multi-gate enforcement:

1. Step-size limits (flex class constraints)
2. Budget balance (zero-sum, strict)
3. Delegation authority (checked by FTL façade, not here)
4. Expenditure limits (spending <= allocation)

Target: 100% test coverage
"""

from decimal import Decimal
from typing import Any

from freedom_that_lasts.budget.models import Budget, BudgetItem, FlexClass
from freedom_that_lasts.kernel.errors import (
    AllocationBelowSpending,
    BudgetBalanceViolation,
    BudgetItemNotFound,
    BudgetNotActive,
    ExpenditureExceedsAllocation,
    FlexStepSizeViolation,
    LawNotFoundForBudget,
)


def validate_flex_step_size(
    item: BudgetItem, change_amount: Decimal, flex_class: FlexClass
) -> None:
    """
    Gate 1: Enforce flex class step-size limits

    CRITICAL: max 5% change per adjustment
    IMPORTANT: max 15% change per adjustment
    ASPIRATIONAL: max 50% change per adjustment

    Args:
        item: Budget item being adjusted
        change_amount: Proposed change (positive or negative)
        flex_class: Flex class of the item

    Raises:
        FlexStepSizeViolation: If change exceeds flex class limit
    """
    # Edge case: if current allocation is zero, allow any increase
    # (can't calculate percentage change from zero)
    if item.allocated_amount == Decimal("0"):
        return

    # Calculate percentage change
    change_percent = abs(change_amount / item.allocated_amount)
    max_percent = flex_class.max_step_percent()

    if change_percent > max_percent:
        raise FlexStepSizeViolation(
            item_id=item.item_id,
            flex_class=flex_class.value,
            change_percent=float(change_percent),
            max_percent=max_percent,
        )


def validate_budget_balance(
    items: dict[str, BudgetItem],
    adjustments: list[dict[str, Any]],
    budget_total: Decimal,
) -> None:
    """
    Gate 2: Ensure adjustments maintain zero-sum (strict balancing)

    Total allocated must equal budget total at all times.
    This prevents unauthorized budget growth or shrinkage.

    Args:
        items: Current budget items
        adjustments: Proposed adjustments [{item_id, change_amount}, ...]
        budget_total: Immutable budget total

    Raises:
        BudgetBalanceViolation: If adjustments break zero-sum constraint
    """
    # Build adjustment map
    adjustment_map: dict[str, Decimal] = {}
    for adj in adjustments:
        item_id = adj["item_id"]
        change = adj["change_amount"]
        adjustment_map[item_id] = adjustment_map.get(item_id, Decimal("0")) + change

    # Calculate new total after adjustments
    new_total = Decimal("0")
    for item_id, item in items.items():
        change = adjustment_map.get(item_id, Decimal("0"))
        new_total += item.allocated_amount + change

    # Strict equality check
    if new_total != budget_total:
        variance = new_total - budget_total
        raise BudgetBalanceViolation(
            budget_total=str(budget_total),
            new_total=str(new_total),
            variance=str(variance),
        )


def validate_expenditure_limit(item: BudgetItem, amount: Decimal) -> None:
    """
    Gate 4: Ensure expenditure doesn't exceed remaining budget

    Args:
        item: Budget item for expenditure
        amount: Expenditure amount

    Raises:
        ExpenditureExceedsAllocation: If amount exceeds remaining budget
    """
    remaining = item.remaining_budget()

    if amount > remaining:
        raise ExpenditureExceedsAllocation(
            item_id=item.item_id,
            amount=str(amount),
            allocated=str(item.allocated_amount),
            spent=str(item.spent_amount),
            remaining=str(remaining),
        )


def validate_no_overspending_after_adjustment(
    item: BudgetItem, new_allocation: Decimal
) -> None:
    """
    Gate 4 (variant): Ensure allocation adjustment doesn't create overspending

    Cannot reduce allocation below current spending.
    This prevents retroactive overspending via allocation reduction.

    Args:
        item: Budget item being adjusted
        new_allocation: Proposed new allocation

    Raises:
        AllocationBelowSpending: If new allocation < current spending
    """
    if new_allocation < item.spent_amount:
        raise AllocationBelowSpending(
            item_id=item.item_id,
            new_allocation=str(new_allocation),
            spent_amount=str(item.spent_amount),
        )


def validate_law_exists(law_id: str, law_registry: Any) -> None:
    """
    Verify law exists before creating budget

    Args:
        law_id: Law ID
        law_registry: Law registry projection

    Raises:
        LawNotFoundForBudget: If law doesn't exist
    """
    law = law_registry.get(law_id)
    if law is None:
        raise LawNotFoundForBudget(law_id=law_id)


def validate_budget_active(budget: Budget) -> None:
    """
    Verify budget is ACTIVE for operations requiring it

    Args:
        budget: Budget to check

    Raises:
        BudgetNotActive: If budget is not ACTIVE
    """
    if not budget.is_active():
        raise BudgetNotActive(
            budget_id=budget.budget_id, current_status=budget.status.value
        )


def validate_budget_item_exists(budget: Budget, item_id: str) -> BudgetItem:
    """
    Verify budget item exists

    Args:
        budget: Budget to search
        item_id: Item ID to find

    Returns:
        BudgetItem if found

    Raises:
        BudgetItemNotFound: If item doesn't exist
    """
    item = budget.get_item(item_id)
    if item is None:
        raise BudgetItemNotFound(budget_id=budget.budget_id, item_id=item_id)
    return item
