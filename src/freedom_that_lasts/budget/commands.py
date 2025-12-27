"""
Budget Module Commands - Intentions to change budget state

Commands represent what users want to do with budgets. They are validated
against multi-gate invariants and converted to events by handlers.

Multi-gate enforcement validates:
1. Step-size limits (flex class constraints)
2. Budget balance (zero-sum, strict)
3. Delegation authority (actor has rights)
4. Expenditure limits (spending <= allocation)
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.budget.models import FlexClass


class BudgetItemSpec(BaseModel):
    """Specification for a budget item during creation"""

    name: str = Field(..., min_length=1, max_length=200)
    allocated_amount: Decimal = Field(..., ge=0)
    flex_class: FlexClass
    category: str = Field(..., min_length=1, max_length=100)


class AdjustmentSpec(BaseModel):
    """Specification for a budget allocation adjustment"""

    item_id: str
    change_amount: Decimal  # Can be positive or negative


class CreateBudget(BaseModel):
    """
    Create a new budget for a law

    Creates a law-scoped budget with multiple line items.
    Budget total is calculated from item allocations and becomes immutable.

    Requirements:
    - Law must exist
    - Items must have positive allocations
    - Total of all allocations becomes budget_total (immutable)
    """

    law_id: str
    fiscal_year: int = Field(..., ge=1900, le=2200)
    items: list[BudgetItemSpec] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivateBudget(BaseModel):
    """
    Activate a budget (DRAFT → ACTIVE)

    Only ACTIVE budgets can:
    - Approve expenditures
    - Have allocations adjusted

    Activation starts the fiscal year.
    """

    budget_id: str


class AdjustAllocation(BaseModel):
    """
    Adjust budget item allocations

    Multi-gate enforcement (ALL must pass):
    1. Step-size limits: Each change respects flex class constraints
    2. Budget balance: Total allocated = budget total (zero-sum)
    3. Delegation authority: Actor has rights in workspace
    4. No overspending: Cannot reduce allocation below current spending

    Adjustments are atomic: all changes applied together or none applied.
    """

    budget_id: str
    adjustments: list[AdjustmentSpec] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=1000)


class ApproveExpenditure(BaseModel):
    """
    Approve an expenditure against a budget item

    Requirements:
    - Budget must be ACTIVE
    - Item must exist
    - Expenditure amount <= remaining budget for item
    - Actor must have delegation authority

    Expenditure is logged as immutable event.
    If any requirement fails, ExpenditureRejected event is emitted.
    """

    budget_id: str
    item_id: str
    amount: Decimal = Field(..., gt=0)
    purpose: str = Field(..., min_length=1, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloseBudget(BaseModel):
    """
    Close a budget (end of fiscal year)

    Transitions budget to CLOSED status.
    No further expenditures or adjustments allowed after closure.
    """

    budget_id: str
    reason: str = Field(..., min_length=1, max_length=1000)


BUDGET_COMMAND_TYPES = {
    "CreateBudget": CreateBudget,
    "ActivateBudget": ActivateBudget,
    "AdjustAllocation": AdjustAllocation,
    "ApproveExpenditure": ApproveExpenditure,
    "CloseBudget": CloseBudget,
}
