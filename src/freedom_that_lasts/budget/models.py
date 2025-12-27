"""
Budget Domain Models - Core entities for budgeting

These models represent the fundamental building blocks of the budget system.
They implement multi-gate enforcement through flex classes, strict balancing,
and expenditure tracking.

Key concepts:
- FlexClass: Graduated step-size limits (5%/15%/50%) for budget adjustments
- Strict Balancing: Total allocated must always equal budget total (zero-sum)
- Law-Scoped: Each budget belongs to exactly one law
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FlexClass(str, Enum):
    """
    Budget item flexibility classification

    Determines maximum percentage change allowed per adjustment:
    - CRITICAL: 5% max step (essential services, hard to cut)
    - IMPORTANT: 15% max step (significant but adjustable)
    - ASPIRATIONAL: 50% max step (nice-to-have, flexible)

    This creates economic barriers to dramatic budget shifts:
    Large changes require many small adjustments, creating full audit trail.
    """

    CRITICAL = "CRITICAL"  # 5% max change per adjustment
    IMPORTANT = "IMPORTANT"  # 15% max change per adjustment
    ASPIRATIONAL = "ASPIRATIONAL"  # 50% max change per adjustment

    def max_step_percent(self) -> float:
        """Get maximum allowed percentage change for this flex class"""
        return {
            FlexClass.CRITICAL: 0.05,
            FlexClass.IMPORTANT: 0.15,
            FlexClass.ASPIRATIONAL: 0.50,
        }[self]


class BudgetStatus(str, Enum):
    """
    Budget lifecycle states

    Budgets move through these states:
    DRAFT → ACTIVE → CLOSED

    Only ACTIVE budgets can approve expenditures.
    """

    DRAFT = "DRAFT"  # Being prepared, not yet active
    ACTIVE = "ACTIVE"  # In effect, can approve expenditures
    CLOSED = "CLOSED"  # Fiscal year ended, archived


class BudgetItem(BaseModel):
    """
    Single line item in a budget

    Each item has:
    - Allocated amount (how much assigned)
    - Spent amount (cumulative expenditures)
    - Flex class (adjustment constraints)
    - Category (for grouping and reporting)

    Invariants enforced:
    - spent_amount <= allocated_amount (no overspending)
    - Adjustments respect flex class step-size limits

    Attributes:
        item_id: Unique identifier within budget
        name: Human-readable name
        allocated_amount: Current allocation
        spent_amount: Cumulative expenditures approved
        flex_class: Adjustment constraint classification
        category: Grouping for reporting (e.g., "personnel", "capital")
    """

    item_id: str
    name: str
    allocated_amount: Decimal = Field(ge=0)
    spent_amount: Decimal = Field(default=Decimal(0), ge=0)
    flex_class: FlexClass
    category: str

    def remaining_budget(self) -> Decimal:
        """Calculate remaining budget for this item"""
        return self.allocated_amount - self.spent_amount

    def max_adjustment_amount(self) -> Decimal:
        """Calculate maximum allowed adjustment based on flex class"""
        max_percent = self.flex_class.max_step_percent()
        return self.allocated_amount * Decimal(str(max_percent))

    def can_spend(self, amount: Decimal) -> bool:
        """Check if expenditure would exceed remaining budget"""
        return amount <= self.remaining_budget()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "item_id": "item-001",
                    "name": "Staff Salaries",
                    "allocated_amount": "500000.00",
                    "spent_amount": "125000.00",
                    "flex_class": "CRITICAL",
                    "category": "personnel",
                }
            ]
        }
    }


class Budget(BaseModel):
    """
    Law-scoped budget with multi-gate enforcement

    Each law has exactly one budget. Budgets implement anti-tyranny safeguards:
    - Flex class step-size limits (prevent sudden cuts to essential services)
    - Strict balancing (total allocated = budget total, always)
    - Expenditure limits (cumulative spending <= allocation)
    - Complete audit trail (all adjustments/expenditures logged as events)

    Attributes:
        budget_id: Unique identifier
        law_id: Parent law (one-to-one relationship)
        fiscal_year: Year this budget covers
        items: Budget line items (keyed by item_id)
        budget_total: Total budget amount (immutable after creation)
        status: Current lifecycle state
        created_at: When budget was created
        activated_at: When budget became active
        closed_at: When budget was closed
        metadata: Additional tracking information
    """

    budget_id: str
    law_id: str
    fiscal_year: int = Field(ge=1900, le=2200)
    items: dict[str, BudgetItem] = Field(default_factory=dict)
    budget_total: Decimal = Field(ge=0)  # Immutable after creation
    status: BudgetStatus = BudgetStatus.DRAFT
    created_at: datetime
    activated_at: datetime | None = None
    closed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def total_allocated(self) -> Decimal:
        """Calculate total currently allocated across all items"""
        return sum(item.allocated_amount for item in self.items.values())

    def total_spent(self) -> Decimal:
        """Calculate total spent across all items"""
        return sum(item.spent_amount for item in self.items.values())

    def total_remaining(self) -> Decimal:
        """Calculate total remaining budget across all items"""
        return sum(item.remaining_budget() for item in self.items.values())

    def is_balanced(self) -> bool:
        """Check if budget maintains strict balance (total allocated = budget total)"""
        return self.total_allocated() == self.budget_total

    def is_active(self) -> bool:
        """Check if budget is currently active"""
        return self.status == BudgetStatus.ACTIVE

    def get_item(self, item_id: str) -> BudgetItem | None:
        """Get budget item by ID"""
        return self.items.get(item_id)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "budget_id": "budget-001",
                    "law_id": "law-health-001",
                    "fiscal_year": 2025,
                    "items": {
                        "item-001": {
                            "item_id": "item-001",
                            "name": "Staff Salaries",
                            "allocated_amount": "500000.00",
                            "spent_amount": "0.00",
                            "flex_class": "CRITICAL",
                            "category": "personnel",
                        },
                        "item-002": {
                            "item_id": "item-002",
                            "name": "Equipment",
                            "allocated_amount": "200000.00",
                            "spent_amount": "0.00",
                            "flex_class": "IMPORTANT",
                            "category": "capital",
                        },
                    },
                    "budget_total": "700000.00",
                    "status": "DRAFT",
                    "created_at": "2025-01-15T10:00:00Z",
                    "activated_at": None,
                    "closed_at": None,
                    "metadata": {"author": "alice", "version": 1},
                }
            ]
        }
    }


class BudgetSummary(BaseModel):
    """
    Lightweight budget summary for lists/dashboards

    Contains just enough info for overview displays
    without loading full budget details.
    """

    budget_id: str
    law_id: str
    fiscal_year: int
    status: BudgetStatus
    budget_total: Decimal
    total_allocated: Decimal
    total_spent: Decimal
    is_balanced: bool
    item_count: int
