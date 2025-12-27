"""
Tests for Budget Triggers - Automatic Budget Health Monitoring

Verifies that budget triggers correctly detect:
- Balance violations (total_allocated != budget_total)
- Expenditure overspending (spent > allocated)
"""

from datetime import datetime
from decimal import Decimal

import pytest

from freedom_that_lasts.budget.triggers import (
    evaluate_budget_balance_trigger,
    evaluate_expenditure_overspend_trigger,
)


def test_budget_balance_trigger_no_violation():
    """Test that no events are emitted when budget is balanced"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "budget_total": "150000",
            "items": {
                "item-1": {"item_id": "item-1", "allocated_amount": "100000"},
                "item-2": {"item_id": "item-2", "allocated_amount": "50000"},
            },
            "version": 1,
        }
    ]

    events = evaluate_budget_balance_trigger(active_budgets, now)
    assert len(events) == 0


def test_budget_balance_trigger_detects_violation():
    """Test that balance violation is detected when total_allocated != budget_total"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "budget_total": "150000",
            "items": {
                "item-1": {"item_id": "item-1", "allocated_amount": "100000"},
                "item-2": {
                    "item_id": "item-2",
                    "allocated_amount": "60000",
                },  # Total is 160k, not 150k!
            },
            "version": 1,
        }
    ]

    events = evaluate_budget_balance_trigger(active_budgets, now)
    assert len(events) == 1

    event = events[0]
    assert event.event_type == "BudgetBalanceViolationDetected"
    assert event.stream_id == "budget-1"
    assert event.payload["budget_total"] == "150000"
    assert event.payload["total_allocated"] == "160000"
    assert event.payload["variance"] == "10000"
    assert event.payload["reason"] == "invariant_violation"


def test_budget_balance_trigger_multiple_budgets():
    """Test that trigger checks all active budgets"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "budget_total": "150000",
            "items": {
                "item-1": {"item_id": "item-1", "allocated_amount": "150000"},
            },
            "version": 1,
        },
        {
            "budget_id": "budget-2",
            "budget_total": "200000",
            "items": {
                "item-1": {"item_id": "item-1", "allocated_amount": "220000"},
            },  # Violation!
            "version": 1,
        },
        {
            "budget_id": "budget-3",
            "budget_total": "100000",
            "items": {
                "item-1": {"item_id": "item-1", "allocated_amount": "100000"},
            },
            "version": 1,
        },
    ]

    events = evaluate_budget_balance_trigger(active_budgets, now)
    assert len(events) == 1
    assert events[0].stream_id == "budget-2"


def test_expenditure_overspend_trigger_no_overspend():
    """Test that no events are emitted when spending is within allocation"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "100000",
                    "spent_amount": "75000",
                },
                "item-2": {
                    "item_id": "item-2",
                    "allocated_amount": "50000",
                    "spent_amount": "0",
                },
            },
            "version": 1,
        }
    ]

    events = evaluate_expenditure_overspend_trigger(active_budgets, now)
    assert len(events) == 0


def test_expenditure_overspend_trigger_detects_overspend():
    """Test that overspending is detected when spent > allocated"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "100000",
                    "spent_amount": "110000",  # Overspend by 10k!
                },
            },
            "version": 1,
        }
    ]

    events = evaluate_expenditure_overspend_trigger(active_budgets, now)
    assert len(events) == 1

    event = events[0]
    assert event.event_type == "BudgetOverspendDetected"
    assert event.stream_id == "budget-1"
    assert event.payload["budget_id"] == "budget-1"
    assert event.payload["item_id"] == "item-1"
    assert event.payload["allocated_amount"] == "100000"
    assert event.payload["spent_amount"] == "110000"
    assert event.payload["overspend_amount"] == "10000"
    assert event.payload["reason"] == "concurrent_expenditure"


def test_expenditure_overspend_trigger_multiple_items():
    """Test that trigger checks all items in all budgets"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "100000",
                    "spent_amount": "105000",  # Overspend!
                },
                "item-2": {
                    "item_id": "item-2",
                    "allocated_amount": "50000",
                    "spent_amount": "45000",  # OK
                },
            },
            "version": 1,
        },
        {
            "budget_id": "budget-2",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "200000",
                    "spent_amount": "250000",  # Overspend!
                },
            },
            "version": 1,
        },
    ]

    events = evaluate_expenditure_overspend_trigger(active_budgets, now)
    assert len(events) == 2

    # Check that both overspends were detected
    overspend_ids = {(e.payload["budget_id"], e.payload["item_id"]) for e in events}
    assert ("budget-1", "item-1") in overspend_ids
    assert ("budget-2", "item-1") in overspend_ids


def test_expenditure_overspend_trigger_exact_allocation():
    """Test that spending exactly the allocation is not flagged"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "100000",
                    "spent_amount": "100000",  # Exactly at limit
                },
            },
            "version": 1,
        }
    ]

    events = evaluate_expenditure_overspend_trigger(active_budgets, now)
    assert len(events) == 0


def test_triggers_with_empty_budget_list():
    """Test that triggers handle empty budget list gracefully"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    balance_events = evaluate_budget_balance_trigger([], now)
    assert len(balance_events) == 0

    overspend_events = evaluate_expenditure_overspend_trigger([], now)
    assert len(overspend_events) == 0


def test_triggers_with_decimal_precision():
    """Test that triggers handle Decimal precision correctly"""
    now = datetime(2025, 3, 15, 12, 0, 0)

    active_budgets = [
        {
            "budget_id": "budget-1",
            "budget_total": "100000.00",
            "items": {
                "item-1": {
                    "item_id": "item-1",
                    "allocated_amount": "100000.00",
                    "spent_amount": "100000.01",  # 1 cent overspend
                },
            },
            "version": 1,
        }
    ]

    # Balance trigger should pass (total matches)
    balance_events = evaluate_budget_balance_trigger(active_budgets, now)
    assert len(balance_events) == 0

    # Overspend trigger should detect the 1 cent overspend
    overspend_events = evaluate_expenditure_overspend_trigger(active_budgets, now)
    assert len(overspend_events) == 1
    assert overspend_events[0].payload["overspend_amount"] == "0.01"
