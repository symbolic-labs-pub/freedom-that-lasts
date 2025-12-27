"""
Budget Module Events - Domain events for budgeting

Events are immutable facts about what happened. They form the
append-only log that is the source of truth for the budget module.

All budget changes (creation, activation, adjustments, expenditures)
are captured as events, creating a complete audit trail.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.budget.models import BudgetStatus, FlexClass


class ItemCreatedSpec(BaseModel):
    """Spec for a budget item creation (in event payload)"""

    item_id: str
    name: str
    allocated_amount: Decimal
    flex_class: FlexClass
    category: str


class AllocationAdjustmentSpec(BaseModel):
    """Spec for an allocation adjustment (in event payload)"""

    item_id: str
    old_amount: Decimal
    new_amount: Decimal
    change_amount: Decimal


class BudgetCreated(BaseModel):
    """
    A new budget was created in DRAFT status

    Budgets start as drafts and must be explicitly activated.
    Budget total is calculated from item allocations and becomes immutable.
    """

    budget_id: str
    law_id: str
    fiscal_year: int
    items: list[ItemCreatedSpec]
    budget_total: Decimal
    created_at: datetime
    created_by: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetActivated(BaseModel):
    """
    A budget moved from DRAFT to ACTIVE

    Only ACTIVE budgets can:
    - Approve expenditures
    - Have allocations adjusted

    Activation starts the fiscal year.
    """

    budget_id: str
    activated_at: datetime
    activated_by: str | None


class AllocationAdjusted(BaseModel):
    """
    Budget allocations were adjusted

    All four gates were validated:
    1. Step-size limits (flex class constraints)
    2. Budget balance (total allocated = budget total)
    3. Delegation authority (actor has rights)
    4. No overspending (allocation >= current spending)

    Adjustments are atomic: all or nothing.
    """

    budget_id: str
    adjusted_at: datetime
    adjustments: list[AllocationAdjustmentSpec]
    reason: str
    adjusted_by: str | None
    gates_validated: list[str] = Field(
        default_factory=lambda: ["step_size", "balance", "authority", "no_overspend"]
    )


class ExpenditureApproved(BaseModel):
    """
    An expenditure was approved against a budget item

    Expenditure passed validation:
    - Budget is ACTIVE
    - Item exists
    - Amount <= remaining budget
    - Actor has authority

    Creates immutable expenditure record.
    """

    budget_id: str
    item_id: str
    expenditure_id: str
    amount: Decimal
    purpose: str
    approved_at: datetime
    approved_by: str | None
    remaining_budget: Decimal  # For item, after this expenditure
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpenditureRejected(BaseModel):
    """
    An expenditure was rejected (failed validation)

    Captures failed expenditure attempts in audit trail.
    Useful for detecting manipulation attempts.
    """

    budget_id: str
    item_id: str
    amount: Decimal
    purpose: str
    rejected_at: datetime
    rejection_reason: str
    gate_failed: str  # Which gate failed: "budget_status", "item_not_found", "insufficient_budget", "authority"


class BudgetClosed(BaseModel):
    """
    A budget was closed (end of fiscal year)

    No further expenditures or adjustments allowed.
    Final state preserves totals for audit.
    """

    budget_id: str
    closed_at: datetime
    reason: str
    final_total_allocated: Decimal
    final_total_spent: Decimal
    final_total_remaining: Decimal


class BudgetBalanceViolationDetected(BaseModel):
    """
    WARNING: Budget balance constraint violated

    This should NEVER happen - indicates invariant bug.
    Emitted by trigger when total_allocated != budget_total.

    Automatic response: System alert, freeze budget adjustments.
    """

    budget_id: str
    detected_at: datetime
    budget_total: Decimal
    total_allocated: Decimal
    variance: Decimal
    reason: str = "invariant_violation"


class BudgetOverspendDetected(BaseModel):
    """
    WARNING: Budget item overspend detected

    Emitted when cumulative expenditures exceed allocation.
    Could indicate:
    - Concurrent expenditure race condition
    - Projection rebuild error
    - Deliberate manipulation attempt

    Automatic response: Flag for review, freeze item expenditures.
    """

    budget_id: str
    item_id: str
    detected_at: datetime
    allocated_amount: Decimal
    spent_amount: Decimal
    overspend_amount: Decimal
    reason: str


BUDGET_EVENT_TYPES = {
    "BudgetCreated": BudgetCreated,
    "BudgetActivated": BudgetActivated,
    "AllocationAdjusted": AllocationAdjusted,
    "ExpenditureApproved": ExpenditureApproved,
    "ExpenditureRejected": ExpenditureRejected,
    "BudgetClosed": BudgetClosed,
    "BudgetBalanceViolationDetected": BudgetBalanceViolationDetected,
    "BudgetOverspendDetected": BudgetOverspendDetected,
}
