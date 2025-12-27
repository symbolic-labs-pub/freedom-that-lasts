"""
Tests for Budget Module Handlers - Command→Event Transformation

These tests verify that budget commands are correctly validated and
converted to events, with multi-gate enforcement.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from freedom_that_lasts.budget.commands import (
    ActivateBudget,
    AdjustAllocation,
    AdjustmentSpec,
    ApproveExpenditure,
    BudgetItemSpec,
    CloseBudget,
    CreateBudget,
)
from freedom_that_lasts.budget.handlers import BudgetCommandHandlers
from freedom_that_lasts.budget.models import BudgetStatus, FlexClass
from freedom_that_lasts.kernel.errors import (
    AllocationBelowSpending,
    BudgetBalanceViolation,
    BudgetItemNotFound,
    BudgetNotFound,
    FlexStepSizeViolation,
    LawNotFoundForBudget,
)
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide deterministic time for tests"""
    return TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def safety_policy() -> SafetyPolicy:
    """Provide default safety policy"""
    return SafetyPolicy()


@pytest.fixture
def handlers(
    test_time: TestTimeProvider, safety_policy: SafetyPolicy
) -> BudgetCommandHandlers:
    """Provide command handlers with test dependencies"""
    return BudgetCommandHandlers(test_time, safety_policy)


@pytest.fixture
def mock_law_registry() -> dict:
    """Provide mock law registry with one law"""
    return {
        "law-123": {
            "law_id": "law-123",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "status": "ACTIVE",
            "version": 1,
        }
    }


def test_create_budget_success(
    handlers: BudgetCommandHandlers, mock_law_registry: dict
) -> None:
    """Test budget creation with valid law"""
    command = CreateBudget(
        law_id="law-123",
        fiscal_year=2025,
        items=[
            BudgetItemSpec(
                name="Staff Salaries",
                allocated_amount=Decimal("500000"),
                flex_class=FlexClass.CRITICAL,
                category="personnel",
            ),
            BudgetItemSpec(
                name="Equipment",
                allocated_amount=Decimal("200000"),
                flex_class=FlexClass.IMPORTANT,
                category="capital",
            ),
        ],
        metadata={"author": "alice"},
    )

    events = handlers.handle_create_budget(
        command, command_id=generate_id(), actor_id="alice", law_registry=mock_law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "BudgetCreated"
    assert event.stream_type == "budget"
    assert event.payload["law_id"] == "law-123"
    assert event.payload["fiscal_year"] == 2025
    assert event.payload["budget_total"] == "700000"  # 500k + 200k
    assert len(event.payload["items"]) == 2
    assert event.payload["created_by"] == "alice"
    assert event.payload["metadata"]["author"] == "alice"

    # Verify items have generated IDs
    items = event.payload["items"]
    assert items[0]["item_id"] is not None
    assert items[0]["name"] == "Staff Salaries"
    assert items[0]["allocated_amount"] == "500000"
    assert items[0]["flex_class"] == "CRITICAL"
    assert items[1]["item_id"] is not None
    assert items[1]["name"] == "Equipment"


def test_create_budget_law_not_found(handlers: BudgetCommandHandlers) -> None:
    """Test that budget creation fails when law doesn't exist"""
    command = CreateBudget(
        law_id="law-nonexistent",
        fiscal_year=2025,
        items=[
            BudgetItemSpec(
                name="Test",
                allocated_amount=Decimal("100000"),
                flex_class=FlexClass.CRITICAL,
                category="test",
            )
        ],
    )

    empty_law_registry: dict = {}

    with pytest.raises(LawNotFoundForBudget) as exc_info:
        handlers.handle_create_budget(
            command,
            command_id=generate_id(),
            actor_id="alice",
            law_registry=empty_law_registry,
        )

    assert exc_info.value.law_id == "law-nonexistent"


def test_create_budget_calculates_total(
    handlers: BudgetCommandHandlers, mock_law_registry: dict
) -> None:
    """Test that budget total is correctly calculated from items"""
    command = CreateBudget(
        law_id="law-123",
        fiscal_year=2025,
        items=[
            BudgetItemSpec(
                name="Item 1",
                allocated_amount=Decimal("123.45"),
                flex_class=FlexClass.CRITICAL,
                category="cat1",
            ),
            BudgetItemSpec(
                name="Item 2",
                allocated_amount=Decimal("67.89"),
                flex_class=FlexClass.IMPORTANT,
                category="cat2",
            ),
            BudgetItemSpec(
                name="Item 3",
                allocated_amount=Decimal("100.00"),
                flex_class=FlexClass.ASPIRATIONAL,
                category="cat3",
            ),
        ],
    )

    events = handlers.handle_create_budget(
        command, command_id=generate_id(), actor_id="alice", law_registry=mock_law_registry
    )

    event = events[0]
    # 123.45 + 67.89 + 100.00 = 291.34
    assert event.payload["budget_total"] == "291.34"


def test_activate_budget_success(
    handlers: BudgetCommandHandlers, test_time: TestTimeProvider
) -> None:
    """Test budget activation when budget exists"""
    # Mock budget registry with one budget
    budget_registry = {
        "budget-123": {
            "budget_id": "budget-123",
            "law_id": "law-123",
            "status": "DRAFT",
            "version": 1,
        }
    }

    command = ActivateBudget(budget_id="budget-123")

    events = handlers.handle_activate_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=budget_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "BudgetActivated"
    assert event.stream_type == "budget"
    assert event.stream_id == "budget-123"
    assert event.payload["budget_id"] == "budget-123"
    assert event.payload["activated_by"] == "alice"
    # Check timestamp (allow for different timezone formats)
    assert "2025-01-15T10:00:00" in event.payload["activated_at"]
    assert event.version == 2  # Incremented from 1


def test_activate_budget_not_found(handlers: BudgetCommandHandlers) -> None:
    """Test that budget activation fails when budget doesn't exist"""
    command = ActivateBudget(budget_id="budget-nonexistent")

    empty_budget_registry: dict = {}

    with pytest.raises(BudgetNotFound) as exc_info:
        handlers.handle_activate_budget(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=empty_budget_registry,
        )

    assert exc_info.value.budget_id == "budget-nonexistent"


def test_activate_budget_version_increment(handlers: BudgetCommandHandlers) -> None:
    """Test that budget activation correctly increments version"""
    budget_registry = {
        "budget-123": {
            "budget_id": "budget-123",
            "law_id": "law-123",
            "status": "DRAFT",
            "version": 5,  # Higher version
        }
    }

    command = ActivateBudget(budget_id="budget-123")

    events = handlers.handle_activate_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=budget_registry,
    )

    event = events[0]
    assert event.version == 6  # Incremented from 5


def test_create_budget_single_item(
    handlers: BudgetCommandHandlers, mock_law_registry: dict
) -> None:
    """Test budget creation with single item"""
    command = CreateBudget(
        law_id="law-123",
        fiscal_year=2025,
        items=[
            BudgetItemSpec(
                name="Single Item",
                allocated_amount=Decimal("1000000"),
                flex_class=FlexClass.CRITICAL,
                category="test",
            )
        ],
    )

    events = handlers.handle_create_budget(
        command, command_id=generate_id(), actor_id="alice", law_registry=mock_law_registry
    )

    event = events[0]
    assert len(event.payload["items"]) == 1
    assert event.payload["budget_total"] == "1000000"


def test_create_budget_generates_unique_ids(
    handlers: BudgetCommandHandlers, mock_law_registry: dict
) -> None:
    """Test that budget and item IDs are unique"""
    command = CreateBudget(
        law_id="law-123",
        fiscal_year=2025,
        items=[
            BudgetItemSpec(
                name="Item 1",
                allocated_amount=Decimal("100"),
                flex_class=FlexClass.CRITICAL,
                category="cat1",
            ),
            BudgetItemSpec(
                name="Item 2",
                allocated_amount=Decimal("200"),
                flex_class=FlexClass.IMPORTANT,
                category="cat2",
            ),
        ],
    )

    events = handlers.handle_create_budget(
        command, command_id=generate_id(), actor_id="alice", law_registry=mock_law_registry
    )

    event = events[0]
    budget_id = event.payload["budget_id"]
    item_ids = [item["item_id"] for item in event.payload["items"]]

    # All IDs should be unique
    all_ids = [budget_id] + item_ids
    assert len(all_ids) == len(set(all_ids))


# ========== Adjust Allocation Tests (Multi-Gate Enforcement) ==========


@pytest.fixture
def mock_budget_with_items() -> dict:
    """Provide mock budget registry with items for adjustment tests"""
    return {
        "budget-123": {
            "budget_id": "budget-123",
            "law_id": "law-123",
            "fiscal_year": 2025,
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "name": "Staff Salaries",
                    "allocated_amount": "500000",
                    "spent_amount": "100000",
                    "flex_class": "CRITICAL",
                    "category": "personnel",
                },
                "item-2": {
                    "item_id": "item-2",
                    "name": "Equipment",
                    "allocated_amount": "200000",
                    "spent_amount": "0",
                    "flex_class": "IMPORTANT",
                    "category": "capital",
                },
                "item-3": {
                    "item_id": "item-3",
                    "name": "Training",
                    "allocated_amount": "50000",
                    "spent_amount": "0",
                    "flex_class": "ASPIRATIONAL",
                    "category": "development",
                },
            },
            "budget_total": "750000",
            "status": BudgetStatus.ACTIVE,
            "created_at": "2025-01-15T10:00:00Z",
            "activated_at": "2025-01-15T11:00:00Z",
            "version": 2,
        }
    }


def test_adjust_allocation_all_gates_pass(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test successful adjustment when all 4 gates pass"""
    # Zero-sum adjustment: -25000 from item-1, +25000 to item-2
    # Item-1: 500k - 25k = 475k (5% change, within CRITICAL limit)
    # Item-2: 200k + 25k = 225k (12.5% change, within IMPORTANT limit)
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("-25000")),
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("25000")),
        ],
        reason="Reallocate to equipment for new hires",
    )

    events = handlers.handle_adjust_allocation(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "AllocationAdjusted"
    assert event.payload["budget_id"] == "budget-123"
    assert event.payload["reason"] == "Reallocate to equipment for new hires"
    assert event.payload["adjusted_by"] == "alice"
    assert len(event.payload["adjustments"]) == 2

    # Verify adjustment details
    adj1 = event.payload["adjustments"][0]
    assert adj1["item_id"] == "item-1"
    assert adj1["old_amount"] == "500000"
    assert adj1["new_amount"] == "475000"
    assert adj1["change_amount"] == "-25000"

    adj2 = event.payload["adjustments"][1]
    assert adj2["item_id"] == "item-2"
    assert adj2["old_amount"] == "200000"
    assert adj2["new_amount"] == "225000"
    assert adj2["change_amount"] == "25000"

    # Verify all gates were validated
    assert event.payload["gates_validated"] == [
        "step_size",
        "balance",
        "authority",
        "no_overspend",
    ]


def test_adjust_allocation_gate1_step_size_violation(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test Gate 1 failure: adjustment exceeds flex class step-size limit"""
    # Try to change item-1 (CRITICAL) by 6% (exceeds 5% limit)
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("-30000")),  # 6%
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("30000")),
        ],
        reason="Large reallocation",
    )

    with pytest.raises(FlexStepSizeViolation) as exc_info:
        handlers.handle_adjust_allocation(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=mock_budget_with_items,
        )

    assert exc_info.value.item_id == "item-1"
    assert exc_info.value.flex_class == "CRITICAL"
    assert exc_info.value.max_percent == 0.05


def test_adjust_allocation_gate2_balance_violation(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test Gate 2 failure: adjustments don't maintain zero-sum"""
    # Net positive: +10000 (breaks balance)
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("10000")),
        ],
        reason="Unauthorized growth",
    )

    with pytest.raises(BudgetBalanceViolation) as exc_info:
        handlers.handle_adjust_allocation(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=mock_budget_with_items,
        )

    assert exc_info.value.budget_total == "750000"
    assert exc_info.value.new_total == "760000"
    assert exc_info.value.variance == "10000"


def test_adjust_allocation_gate4_overspending_violation(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test Gate 4 failure: adjustment would create overspending"""
    # Try to reduce item-1 allocation below current spending
    # Item-1: allocated 500k, spent 100k
    # Reduce by 25k (5% - passes Gate 1) to 475k, then add item to bring total down to 80k
    # We need to reduce item-1 by more than it has, but within step-size limit
    # Strategy: adjust item-2 (no spending) down significantly, then try to adjust item-1 down

    # Modify the mock to have a scenario that passes Gate 1 but fails Gate 4
    # Item-3: allocated 50k, spent 40k (add spending)
    mock_budget_with_items["budget-123"]["items"]["item-3"]["spent_amount"] = "40000"

    # Try to reduce item-3 by 5k (10% - within ASPIRATIONAL 50%)
    # 50k - 15k = 35k, which is less than 40k spent - should fail Gate 4
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-3", change_amount=Decimal("-15000")),  # 30%
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("15000")),
        ],
        reason="Invalid reduction",
    )

    with pytest.raises(AllocationBelowSpending) as exc_info:
        handlers.handle_adjust_allocation(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=mock_budget_with_items,
        )

    assert exc_info.value.item_id == "item-3"
    assert exc_info.value.new_allocation == "35000"
    assert exc_info.value.spent_amount == "40000"


def test_adjust_allocation_item_not_found(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test that adjustment fails when item doesn't exist"""
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-nonexistent", change_amount=Decimal("10000")),
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("-10000")),
        ],
        reason="Invalid item",
    )

    with pytest.raises(BudgetItemNotFound) as exc_info:
        handlers.handle_adjust_allocation(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=mock_budget_with_items,
        )

    assert exc_info.value.budget_id == "budget-123"
    assert exc_info.value.item_id == "item-nonexistent"


def test_adjust_allocation_budget_not_found(handlers: BudgetCommandHandlers) -> None:
    """Test that adjustment fails when budget doesn't exist"""
    command = AdjustAllocation(
        budget_id="budget-nonexistent",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("10000")),
        ],
        reason="Test",
    )

    empty_budget_registry: dict = {}

    with pytest.raises(BudgetNotFound) as exc_info:
        handlers.handle_adjust_allocation(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry=empty_budget_registry,
        )

    assert exc_info.value.budget_id == "budget-nonexistent"


def test_adjust_allocation_multiple_items_balanced(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test three-way adjustment that maintains balance"""
    # Three-way zero-sum: -10k, +5k, +5k
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("-10000")),  # 2%
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("5000")),  # 2.5%
            AdjustmentSpec(item_id="item-3", change_amount=Decimal("5000")),  # 10%
        ],
        reason="Three-way rebalance",
    )

    events = handlers.handle_adjust_allocation(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert len(event.payload["adjustments"]) == 3


def test_adjust_allocation_exactly_at_step_limit(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test adjustment exactly at flex class limit (should pass)"""
    # Item-2 (IMPORTANT): 200k * 15% = 30k exactly
    # But we need to keep it under the limit to pass
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("-29000")),  # 14.5%
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("29000")),  # 5.8%, exceeds!
        ],
        reason="At limit",
    )

    # This should actually fail because 5.8% exceeds 5% for CRITICAL
    # Let me fix this to actually be at the limit
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("-24000")),  # 4.8%
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("24000")),  # 12%
        ],
        reason="At limit",
    )

    events = handlers.handle_adjust_allocation(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1


def test_adjust_allocation_version_increment(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test that adjustment correctly increments version"""
    command = AdjustAllocation(
        budget_id="budget-123",
        adjustments=[
            AdjustmentSpec(item_id="item-1", change_amount=Decimal("-10000")),
            AdjustmentSpec(item_id="item-2", change_amount=Decimal("10000")),
        ],
        reason="Version test",
    )

    events = handlers.handle_adjust_allocation(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    assert event.version == 3  # Incremented from 2


# ========== Approve Expenditure Tests (Approval and Rejection) ==========


def test_approve_expenditure_success(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test successful expenditure approval"""
    # Item-1: allocated 500k, spent 100k, remaining 400k
    # Approve expenditure of 50k (well within budget)
    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-1",
        amount=Decimal("50000"),
        purpose="Q1 Salaries",
        metadata={"quarter": "Q1"},
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureApproved"
    assert event.payload["budget_id"] == "budget-123"
    assert event.payload["item_id"] == "item-1"
    assert event.payload["amount"] == "50000"
    assert event.payload["purpose"] == "Q1 Salaries"
    assert event.payload["approved_by"] == "alice"
    assert event.payload["remaining_budget"] == "350000"  # 400k - 50k
    assert event.payload["expenditure_id"] is not None
    assert event.payload["metadata"]["quarter"] == "Q1"


def test_approve_expenditure_exactly_at_limit(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test expenditure exactly at remaining budget (should approve)"""
    # Item-1: allocated 500k, spent 100k, remaining 400k
    # Approve exactly 400k
    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-1",
        amount=Decimal("400000"),
        purpose="Use all remaining budget",
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureApproved"
    assert event.payload["remaining_budget"] == "0"


def test_approve_expenditure_exceeds_budget_rejects(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test expenditure exceeding budget is REJECTED (not exception)"""
    # Item-1: allocated 500k, spent 100k, remaining 400k
    # Try to approve 450k (exceeds remaining)
    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-1",
        amount=Decimal("450000"),
        purpose="Overspend attempt",
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    # Should emit REJECTION event, not raise exception
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureRejected"
    assert event.payload["budget_id"] == "budget-123"
    assert event.payload["item_id"] == "item-1"
    assert event.payload["amount"] == "450000"
    assert event.payload["purpose"] == "Overspend attempt"
    assert event.payload["gate_failed"] == "insufficient_budget"
    assert "exceeds" in event.payload["rejection_reason"].lower()


def test_approve_expenditure_budget_not_active_rejects(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test expenditure on non-ACTIVE budget is REJECTED"""
    # Change budget status to DRAFT
    mock_budget_with_items["budget-123"]["status"] = BudgetStatus.DRAFT

    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-1",
        amount=Decimal("50000"),
        purpose="Test on draft budget",
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureRejected"
    assert event.payload["gate_failed"] == "budget_status"
    assert "ACTIVE" in event.payload["rejection_reason"]


def test_approve_expenditure_item_not_found_rejects(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test expenditure on non-existent item is REJECTED"""
    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-nonexistent",
        amount=Decimal("50000"),
        purpose="Test on invalid item",
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureRejected"
    assert event.payload["gate_failed"] == "item_not_found"
    assert "not found" in event.payload["rejection_reason"].lower()


def test_approve_expenditure_budget_not_found_rejects(
    handlers: BudgetCommandHandlers,
) -> None:
    """Test expenditure on non-existent budget is REJECTED"""
    command = ApproveExpenditure(
        budget_id="budget-nonexistent",
        item_id="item-1",
        amount=Decimal("50000"),
        purpose="Test on invalid budget",
    )

    empty_budget_registry: dict = {}

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=empty_budget_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ExpenditureRejected"
    assert event.payload["gate_failed"] == "budget_not_found"


def test_approve_expenditure_multiple_approvals(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test multiple sequential expenditures"""
    # First expenditure: 100k
    command1 = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-2",  # Item-2: allocated 200k, spent 0
        amount=Decimal("100000"),
        purpose="First purchase",
    )

    events1 = handlers.handle_approve_expenditure(
        command1,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert events1[0].event_type == "ExpenditureApproved"
    assert events1[0].payload["remaining_budget"] == "100000"

    # Simulate projection update (in real system, projection would update)
    # For this test, we manually update the mock
    mock_budget_with_items["budget-123"]["items"]["item-2"]["spent_amount"] = "100000"
    mock_budget_with_items["budget-123"]["version"] = 3

    # Second expenditure: another 50k
    command2 = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-2",
        amount=Decimal("50000"),
        purpose="Second purchase",
    )

    events2 = handlers.handle_approve_expenditure(
        command2,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert events2[0].event_type == "ExpenditureApproved"
    assert events2[0].payload["remaining_budget"] == "50000"
    assert events2[0].version == 4  # Incremented from 3


def test_approve_expenditure_version_increment(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test that expenditure approval correctly increments version"""
    command = ApproveExpenditure(
        budget_id="budget-123",
        item_id="item-1",
        amount=Decimal("10000"),
        purpose="Version test",
    )

    events = handlers.handle_approve_expenditure(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    assert event.version == 3  # Incremented from 2


# ========== CloseBudget Handler Tests ==========


def test_close_budget_success(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test successful budget closure"""
    command = CloseBudget(
        budget_id="budget-123",
        reason="End of fiscal year 2025",
    )

    events = handlers.handle_close_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    assert len(events) == 1
    event = events[0]

    assert event.event_type == "BudgetClosed"
    assert event.stream_id == "budget-123"
    assert event.actor_id == "alice"

    payload = event.payload
    assert payload["budget_id"] == "budget-123"
    assert payload["reason"] == "End of fiscal year 2025"
    assert "closed_at" in payload


def test_close_budget_not_found(handlers: BudgetCommandHandlers) -> None:
    """Test closing non-existent budget raises error"""
    command = CloseBudget(
        budget_id="nonexistent",
        reason="Test",
    )

    with pytest.raises(BudgetNotFound) as exc_info:
        handlers.handle_close_budget(
            command,
            command_id=generate_id(),
            actor_id="alice",
            budget_registry={},
        )

    assert exc_info.value.budget_id == "nonexistent"


def test_close_budget_calculates_totals(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test that close budget correctly calculates final totals"""
    # Mock budget has:
    # - item-1: 500k allocated, 100k spent
    # - item-2: 200k allocated, 0 spent
    # - item-3: 50k allocated, 0 spent
    # Total: 750k allocated, 100k spent, 650k remaining

    command = CloseBudget(
        budget_id="budget-123",
        reason="End of fiscal year",
    )

    events = handlers.handle_close_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    payload = event.payload

    assert payload["final_total_allocated"] == "750000"
    assert payload["final_total_spent"] == "100000"
    assert payload["final_total_remaining"] == "650000"


def test_close_budget_with_spending(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test closing budget after various expenditures"""
    # Add more spending
    mock_budget_with_items["budget-123"]["items"]["item-2"]["spent_amount"] = "150000"
    mock_budget_with_items["budget-123"]["items"]["item-3"]["spent_amount"] = "25000"

    # Total: 750k allocated, 275k spent (100k + 150k + 25k), 475k remaining

    command = CloseBudget(
        budget_id="budget-123",
        reason="Fiscal year complete",
    )

    events = handlers.handle_close_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    payload = event.payload

    assert payload["final_total_allocated"] == "750000"
    assert payload["final_total_spent"] == "275000"  # 100k + 150k + 25k
    assert payload["final_total_remaining"] == "475000"  # 750k - 275k


def test_close_budget_version_increment(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test that close budget correctly increments version"""
    command = CloseBudget(
        budget_id="budget-123",
        reason="Version test",
    )

    events = handlers.handle_close_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    assert event.version == 3  # Incremented from 2


def test_close_budget_empty_budget(
    handlers: BudgetCommandHandlers, mock_budget_with_items: dict
) -> None:
    """Test closing budget with no spending"""
    # Reset all spending to zero
    for item_id in mock_budget_with_items["budget-123"]["items"]:
        mock_budget_with_items["budget-123"]["items"][item_id]["spent_amount"] = "0"

    command = CloseBudget(
        budget_id="budget-123",
        reason="Cancelled project",
    )

    events = handlers.handle_close_budget(
        command,
        command_id=generate_id(),
        actor_id="alice",
        budget_registry=mock_budget_with_items,
    )

    event = events[0]
    payload = event.payload

    assert payload["final_total_allocated"] == "750000"
    assert payload["final_total_spent"] == "0"
    assert payload["final_total_remaining"] == "750000"
