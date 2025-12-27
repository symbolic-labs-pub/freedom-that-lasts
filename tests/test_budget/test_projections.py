"""
Tests for Budget Module Projections - Read Model Event Application

These tests verify that projections correctly build read models from events.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from freedom_that_lasts.budget.models import BudgetStatus
from freedom_that_lasts.budget.projections import (
    BudgetHealthProjection,
    BudgetRegistry,
    ExpenditureLog,
)
from freedom_that_lasts.kernel.events import create_event
from freedom_that_lasts.kernel.ids import generate_id


# ========== Fixtures ==========


@pytest.fixture
def budget_created_event() -> dict:
    """Sample BudgetCreated event"""
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    payload = {
        "budget_id": "budget-123",
        "law_id": "law-456",
        "fiscal_year": 2025,
        "items": [
            {
                "item_id": "item-1",
                "name": "Staff Salaries",
                "allocated_amount": "500000",
                "flex_class": "CRITICAL",
                "category": "personnel",
            },
            {
                "item_id": "item-2",
                "name": "Equipment",
                "allocated_amount": "200000",
                "flex_class": "IMPORTANT",
                "category": "capital",
            },
        ],
        "budget_total": "700000",
        "created_at": now.isoformat(),
        "created_by": "alice",
        "metadata": {},
    }

    return create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload,
        version=1,
    )


# ========== BudgetRegistry Tests ==========


def test_budget_registry_apply_budget_created(budget_created_event) -> None:
    """Test that BudgetCreated event creates budget in registry"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    budget = registry.get("budget-123")
    assert budget is not None
    assert budget["budget_id"] == "budget-123"
    assert budget["law_id"] == "law-456"
    assert budget["fiscal_year"] == 2025
    assert budget["budget_total"] == "700000"
    assert budget["status"] == BudgetStatus.DRAFT.value
    assert budget["version"] == 1

    # Check items
    assert len(budget["items"]) == 2
    assert budget["items"]["item-1"]["name"] == "Staff Salaries"
    assert budget["items"]["item-1"]["allocated_amount"] == "500000"
    assert budget["items"]["item-1"]["spent_amount"] == "0"
    assert budget["items"]["item-1"]["flex_class"] == "CRITICAL"


def test_budget_registry_apply_budget_activated(budget_created_event) -> None:
    """Test that BudgetActivated event sets status to ACTIVE"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    now = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
    activated_payload = {
        "budget_id": "budget-123",
        "activated_at": now.isoformat(),
        "activated_by": "alice",
    }

    activated_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetActivated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=activated_payload,
        version=2,
    )

    registry.apply_event(activated_event)

    budget = registry.get("budget-123")
    assert budget["status"] == BudgetStatus.ACTIVE.value
    assert budget["activated_at"] == now.isoformat()
    assert budget["version"] == 2


def test_budget_registry_apply_allocation_adjusted(budget_created_event) -> None:
    """Test that AllocationAdjusted event updates item allocations"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    adjusted_payload = {
        "budget_id": "budget-123",
        "adjusted_at": now.isoformat(),
        "adjustments": [
            {
                "item_id": "item-1",
                "old_amount": "500000",
                "new_amount": "475000",
                "change_amount": "-25000",
            },
            {
                "item_id": "item-2",
                "old_amount": "200000",
                "new_amount": "225000",
                "change_amount": "25000",
            },
        ],
        "reason": "Reallocate to equipment",
        "adjusted_by": "alice",
        "gates_validated": ["step_size", "balance", "authority", "no_overspend"],
    }

    adjusted_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="AllocationAdjusted",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=adjusted_payload,
        version=2,
    )

    registry.apply_event(adjusted_event)

    budget = registry.get("budget-123")
    assert budget["items"]["item-1"]["allocated_amount"] == "475000"
    assert budget["items"]["item-2"]["allocated_amount"] == "225000"
    assert budget["version"] == 2


def test_budget_registry_apply_expenditure_approved(budget_created_event) -> None:
    """Test that ExpenditureApproved event increments spent amount"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    expenditure_payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "expenditure_id": "exp-1",
        "amount": "50000",
        "purpose": "Hire analyst",
        "approved_at": now.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "450000",
        "metadata": {},
    }

    expenditure_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=expenditure_payload,
        version=2,
    )

    registry.apply_event(expenditure_event)

    budget = registry.get("budget-123")
    assert budget["items"]["item-1"]["spent_amount"] == "50000"
    assert budget["version"] == 2


def test_budget_registry_apply_multiple_expenditures(budget_created_event) -> None:
    """Test that multiple expenditures accumulate spent amount"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    # First expenditure: 50k
    now1 = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    exp1_payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "expenditure_id": "exp-1",
        "amount": "50000",
        "purpose": "First",
        "approved_at": now1.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "450000",
    }

    exp1_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now1,
        command_id=generate_id(),
        actor_id="alice",
        payload=exp1_payload,
        version=2,
    )

    registry.apply_event(exp1_event)

    # Second expenditure: 30k (total 80k)
    now2 = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    exp2_payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "expenditure_id": "exp-2",
        "amount": "30000",
        "purpose": "Second",
        "approved_at": now2.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "420000",
    }

    exp2_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now2,
        command_id=generate_id(),
        actor_id="alice",
        payload=exp2_payload,
        version=3,
    )

    registry.apply_event(exp2_event)

    budget = registry.get("budget-123")
    assert budget["items"]["item-1"]["spent_amount"] == "80000"  # 50k + 30k


def test_budget_registry_apply_budget_closed(budget_created_event) -> None:
    """Test that BudgetClosed event sets status to CLOSED"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    now = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    closed_payload = {
        "budget_id": "budget-123",
        "closed_at": now.isoformat(),
        "reason": "End of fiscal year",
        "final_total_allocated": "700000",
        "final_total_spent": "450000",
        "final_total_remaining": "250000",
    }

    closed_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetClosed",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=closed_payload,
        version=2,
    )

    registry.apply_event(closed_event)

    budget = registry.get("budget-123")
    assert budget["status"] == BudgetStatus.CLOSED.value
    assert budget["closed_at"] == now.isoformat()
    assert budget["version"] == 2


def test_budget_registry_list_by_law(budget_created_event) -> None:
    """Test listing budgets by law"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    # Create another budget for same law
    now = datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
    payload2 = {
        "budget_id": "budget-456",
        "law_id": "law-456",
        "fiscal_year": 2026,
        "items": [],
        "budget_total": "800000",
        "created_at": now.isoformat(),
        "created_by": "bob",
        "metadata": {},
    }

    event2 = create_event(
        event_id=generate_id(),
        stream_id="budget-456",
        stream_type="budget",
        event_type="BudgetCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="bob",
        payload=payload2,
        version=1,
    )

    registry.apply_event(event2)

    # Create budget for different law
    payload3 = {
        "budget_id": "budget-789",
        "law_id": "law-999",
        "fiscal_year": 2025,
        "items": [],
        "budget_total": "100000",
        "created_at": now.isoformat(),
        "created_by": "carol",
        "metadata": {},
    }

    event3 = create_event(
        event_id=generate_id(),
        stream_id="budget-789",
        stream_type="budget",
        event_type="BudgetCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="carol",
        payload=payload3,
        version=1,
    )

    registry.apply_event(event3)

    budgets = registry.list_by_law("law-456")
    assert len(budgets) == 2
    assert all(b["law_id"] == "law-456" for b in budgets)


def test_budget_registry_list_by_status(budget_created_event) -> None:
    """Test listing budgets by status"""
    registry = BudgetRegistry()
    registry.apply_event(budget_created_event)

    # Activate the budget
    now = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
    activated_payload = {
        "budget_id": "budget-123",
        "activated_at": now.isoformat(),
        "activated_by": "alice",
    }

    activated_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetActivated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=activated_payload,
        version=2,
    )

    registry.apply_event(activated_event)

    # Create another DRAFT budget
    payload2 = {
        "budget_id": "budget-456",
        "law_id": "law-789",
        "fiscal_year": 2026,
        "items": [],
        "budget_total": "500000",
        "created_at": now.isoformat(),
        "created_by": "bob",
        "metadata": {},
    }

    event2 = create_event(
        event_id=generate_id(),
        stream_id="budget-456",
        stream_type="budget",
        event_type="BudgetCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="bob",
        payload=payload2,
        version=1,
    )

    registry.apply_event(event2)

    active_budgets = registry.list_by_status(BudgetStatus.ACTIVE)
    assert len(active_budgets) == 1
    assert active_budgets[0]["budget_id"] == "budget-123"

    draft_budgets = registry.list_by_status(BudgetStatus.DRAFT)
    assert len(draft_budgets) == 1
    assert draft_budgets[0]["budget_id"] == "budget-456"


def test_budget_registry_list_active() -> None:
    """Test list_active convenience method"""
    registry = BudgetRegistry()

    # Create and activate budget
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    created_payload = {
        "budget_id": "budget-123",
        "law_id": "law-456",
        "fiscal_year": 2025,
        "items": [],
        "budget_total": "100000",
        "created_at": now.isoformat(),
        "created_by": "alice",
        "metadata": {},
    }

    created_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=created_payload,
        version=1,
    )

    registry.apply_event(created_event)

    activated_payload = {
        "budget_id": "budget-123",
        "activated_at": now.isoformat(),
        "activated_by": "alice",
    }

    activated_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetActivated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=activated_payload,
        version=2,
    )

    registry.apply_event(activated_event)

    active_budgets = registry.list_active()
    assert len(active_budgets) == 1
    assert active_budgets[0]["status"] == BudgetStatus.ACTIVE.value


# ========== ExpenditureLog Tests ==========


def test_expenditure_log_apply_expenditure_approved() -> None:
    """Test that ExpenditureApproved event is logged"""
    log = ExpenditureLog()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "expenditure_id": "exp-1",
        "amount": "50000",
        "purpose": "Hire analyst",
        "approved_at": now.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "450000",
        "metadata": {"department": "IT"},
    }

    event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload,
        version=2,
    )

    log.apply_event(event)

    assert len(log.expenditures) == 1
    exp = log.expenditures[0]
    assert exp["expenditure_id"] == "exp-1"
    assert exp["budget_id"] == "budget-123"
    assert exp["amount"] == "50000"
    assert exp["purpose"] == "Hire analyst"
    assert exp["metadata"]["department"] == "IT"


def test_expenditure_log_apply_expenditure_rejected() -> None:
    """Test that ExpenditureRejected event is logged"""
    log = ExpenditureLog()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "amount": "600000",
        "purpose": "Exceeds budget",
        "rejected_at": now.isoformat(),
        "rejection_reason": "Expenditure exceeds allocation",
        "gate_failed": "insufficient_budget",
    }

    event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureRejected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload,
        version=2,
    )

    log.apply_event(event)

    assert len(log.rejections) == 1
    rej = log.rejections[0]
    assert rej["budget_id"] == "budget-123"
    assert rej["amount"] == "600000"
    assert rej["rejection_reason"] == "Expenditure exceeds allocation"
    assert rej["gate_failed"] == "insufficient_budget"


def test_expenditure_log_get_by_budget() -> None:
    """Test querying expenditures by budget"""
    log = ExpenditureLog()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

    # Add expenditure for budget-123
    payload1 = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "expenditure_id": "exp-1",
        "amount": "50000",
        "purpose": "First",
        "approved_at": now.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "450000",
    }

    event1 = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload1,
        version=2,
    )

    log.apply_event(event1)

    # Add expenditure for budget-456
    payload2 = {
        "budget_id": "budget-456",
        "item_id": "item-2",
        "expenditure_id": "exp-2",
        "amount": "30000",
        "purpose": "Second",
        "approved_at": now.isoformat(),
        "approved_by": "bob",
        "remaining_budget": "170000",
    }

    event2 = create_event(
        event_id=generate_id(),
        stream_id="budget-456",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="bob",
        payload=payload2,
        version=2,
    )

    log.apply_event(event2)

    # Query by budget
    budget_123_exp = log.get_by_budget("budget-123")
    assert len(budget_123_exp) == 1
    assert budget_123_exp[0]["expenditure_id"] == "exp-1"


def test_expenditure_log_get_by_item() -> None:
    """Test querying expenditures by budget item"""
    log = ExpenditureLog()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

    # Add two expenditures for item-1
    for i in range(2):
        payload = {
            "budget_id": "budget-123",
            "item_id": "item-1",
            "expenditure_id": f"exp-{i}",
            "amount": "10000",
            "purpose": f"Expenditure {i}",
            "approved_at": now.isoformat(),
            "approved_by": "alice",
            "remaining_budget": "480000",
        }

        event = create_event(
            event_id=generate_id(),
            stream_id="budget-123",
            stream_type="budget",
            event_type="ExpenditureApproved",
            occurred_at=now,
            command_id=generate_id(),
            actor_id="alice",
            payload=payload,
            version=i + 2,
        )

        log.apply_event(event)

    # Add one expenditure for item-2
    payload3 = {
        "budget_id": "budget-123",
        "item_id": "item-2",
        "expenditure_id": "exp-2",
        "amount": "5000",
        "purpose": "Different item",
        "approved_at": now.isoformat(),
        "approved_by": "alice",
        "remaining_budget": "195000",
    }

    event3 = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureApproved",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload3,
        version=4,
    )

    log.apply_event(event3)

    # Query by item
    item_1_exp = log.get_by_item("budget-123", "item-1")
    assert len(item_1_exp) == 2

    item_2_exp = log.get_by_item("budget-123", "item-2")
    assert len(item_2_exp) == 1


def test_expenditure_log_get_rejections() -> None:
    """Test querying rejections"""
    log = ExpenditureLog()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

    # Add rejection for budget-123
    payload1 = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "amount": "600000",
        "purpose": "Too much",
        "rejected_at": now.isoformat(),
        "rejection_reason": "Exceeds budget",
        "gate_failed": "insufficient_budget",
    }

    event1 = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="ExpenditureRejected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload=payload1,
        version=2,
    )

    log.apply_event(event1)

    # Add rejection for budget-456
    payload2 = {
        "budget_id": "budget-456",
        "item_id": "item-2",
        "amount": "50000",
        "purpose": "Not active",
        "rejected_at": now.isoformat(),
        "rejection_reason": "Budget not active",
        "gate_failed": "budget_status",
    }

    event2 = create_event(
        event_id=generate_id(),
        stream_id="budget-456",
        stream_type="budget",
        event_type="ExpenditureRejected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="bob",
        payload=payload2,
        version=2,
    )

    log.apply_event(event2)

    # Get all rejections
    all_rejections = log.get_rejections()
    assert len(all_rejections) == 2

    # Get rejections for specific budget
    budget_123_rejections = log.get_rejections("budget-123")
    assert len(budget_123_rejections) == 1
    assert budget_123_rejections[0]["gate_failed"] == "insufficient_budget"


# ========== BudgetHealthProjection Tests ==========


def test_budget_health_apply_balance_violation() -> None:
    """Test that balance violation is logged"""
    health = BudgetHealthProjection()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    payload = {
        "budget_id": "budget-123",
        "detected_at": now.isoformat(),
        "budget_total": "700000",
        "total_allocated": "710000",
        "variance": "10000",
        "reason": "invariant_violation",
    }

    event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetBalanceViolationDetected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id=None,
        payload=payload,
        version=5,
    )

    health.apply_event(event)

    assert len(health.balance_violations) == 1
    violation = health.balance_violations[0]
    assert violation["budget_id"] == "budget-123"
    assert violation["variance"] == "10000"


def test_budget_health_apply_overspend_detected() -> None:
    """Test that overspend is logged"""
    health = BudgetHealthProjection()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    payload = {
        "budget_id": "budget-123",
        "item_id": "item-1",
        "detected_at": now.isoformat(),
        "allocated_amount": "500000",
        "spent_amount": "510000",
        "overspend_amount": "10000",
        "reason": "concurrent_expenditure",
    }

    event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetOverspendDetected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id=None,
        payload=payload,
        version=5,
    )

    health.apply_event(event)

    assert len(health.overspend_incidents) == 1
    incident = health.overspend_incidents[0]
    assert incident["budget_id"] == "budget-123"
    assert incident["item_id"] == "item-1"
    assert incident["overspend_amount"] == "10000"


def test_budget_health_has_violations() -> None:
    """Test checking if budget has violations"""
    health = BudgetHealthProjection()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

    # Add balance violation for budget-123
    balance_payload = {
        "budget_id": "budget-123",
        "detected_at": now.isoformat(),
        "budget_total": "700000",
        "total_allocated": "710000",
        "variance": "10000",
        "reason": "invariant_violation",
    }

    balance_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetBalanceViolationDetected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id=None,
        payload=balance_payload,
        version=5,
    )

    health.apply_event(balance_event)

    assert health.has_violations("budget-123") is True
    assert health.has_violations("budget-456") is False


def test_budget_health_get_violations() -> None:
    """Test getting violations for budget"""
    health = BudgetHealthProjection()

    now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

    # Add balance violation for budget-123
    balance_payload = {
        "budget_id": "budget-123",
        "detected_at": now.isoformat(),
        "budget_total": "700000",
        "total_allocated": "710000",
        "variance": "10000",
        "reason": "invariant_violation",
    }

    balance_event = create_event(
        event_id=generate_id(),
        stream_id="budget-123",
        stream_type="budget",
        event_type="BudgetBalanceViolationDetected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id=None,
        payload=balance_payload,
        version=5,
    )

    health.apply_event(balance_event)

    # Add overspend for budget-456
    overspend_payload = {
        "budget_id": "budget-456",
        "item_id": "item-2",
        "detected_at": now.isoformat(),
        "allocated_amount": "200000",
        "spent_amount": "205000",
        "overspend_amount": "5000",
        "reason": "concurrent_expenditure",
    }

    overspend_event = create_event(
        event_id=generate_id(),
        stream_id="budget-456",
        stream_type="budget",
        event_type="BudgetOverspendDetected",
        occurred_at=now,
        command_id=generate_id(),
        actor_id=None,
        payload=overspend_payload,
        version=5,
    )

    health.apply_event(overspend_event)

    # Get violations for budget-123
    budget_123_violations = health.get_violations("budget-123")
    assert len(budget_123_violations["balance_violations"]) == 1
    assert len(budget_123_violations["overspend_incidents"]) == 0

    # Get all violations
    all_violations = health.get_violations()
    assert len(all_violations["balance_violations"]) == 1
    assert len(all_violations["overspend_incidents"]) == 1
