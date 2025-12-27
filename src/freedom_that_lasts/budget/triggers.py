"""
Budget Module Triggers - Automatic Budget Health Monitoring

Triggers are automatic responses to budget anomalies.
They evaluate budget state and emit reflex events (warnings).

This is the budget "immune system" - it detects violations
and overspending automatically.
"""

from datetime import datetime
from decimal import Decimal

from freedom_that_lasts.budget.events import (
    BudgetBalanceViolationDetected,
    BudgetOverspendDetected,
)
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id


def evaluate_budget_balance_trigger(
    active_budgets: list[dict],
    now: datetime,
) -> list[Event]:
    """
    Evaluate budget balance constraint for all active budgets

    This checks that total_allocated == budget_total for every budget.
    If not, a balance violation is detected.

    NOTE: This should NEVER trigger if invariants are working correctly.
    If it does trigger, it indicates a bug in the invariant validation.

    Args:
        active_budgets: List of ACTIVE budget dicts
        now: Current time

    Returns:
        List of BudgetBalanceViolationDetected events
    """
    events: list[Event] = []

    for budget in active_budgets:
        # Calculate total allocated
        total_allocated = sum(
            Decimal(str(item["allocated_amount"]))
            for item in budget["items"].values()
        )
        budget_total = Decimal(str(budget["budget_total"]))

        # Check if balance is violated
        if total_allocated != budget_total:
            variance = total_allocated - budget_total

            violation_event = Event(
                event_id=generate_id(),
                stream_id=budget["budget_id"],
                stream_type="budget",
                version=budget.get("version", 1) + 1,
                command_id=generate_id(),
                event_type="BudgetBalanceViolationDetected",
                occurred_at=now,
                actor_id="system",
                payload=BudgetBalanceViolationDetected(
                    budget_id=budget["budget_id"],
                    detected_at=now,
                    budget_total=budget_total,
                    total_allocated=total_allocated,
                    variance=variance,
                    reason="invariant_violation",
                ).model_dump(mode="json"),
            )
            events.append(violation_event)

    return events


def evaluate_expenditure_overspend_trigger(
    active_budgets: list[dict],
    now: datetime,
) -> list[Event]:
    """
    Evaluate expenditure limits for all active budget items

    This checks that spent_amount <= allocated_amount for every item.
    If not, an overspend is detected.

    Overspending can occur due to:
    - Concurrent expenditure approvals (race condition)
    - Projection rebuild errors
    - Deliberate manipulation attempts

    Args:
        active_budgets: List of ACTIVE budget dicts
        now: Current time

    Returns:
        List of BudgetOverspendDetected events
    """
    events: list[Event] = []

    for budget in active_budgets:
        for item in budget["items"].values():
            allocated = Decimal(str(item["allocated_amount"]))
            spent = Decimal(str(item["spent_amount"]))

            # Check if overspending occurred
            if spent > allocated:
                overspend = spent - allocated

                overspend_event = Event(
                    event_id=generate_id(),
                    stream_id=budget["budget_id"],
                    stream_type="budget",
                    version=budget.get("version", 1) + 1,
                    command_id=generate_id(),
                    event_type="BudgetOverspendDetected",
                    occurred_at=now,
                    actor_id="system",
                    payload=BudgetOverspendDetected(
                        budget_id=budget["budget_id"],
                        item_id=item["item_id"],
                        detected_at=now,
                        allocated_amount=allocated,
                        spent_amount=spent,
                        overspend_amount=overspend,
                        reason="concurrent_expenditure",
                    ).model_dump(mode="json"),
                )
                events.append(overspend_event)

    return events
