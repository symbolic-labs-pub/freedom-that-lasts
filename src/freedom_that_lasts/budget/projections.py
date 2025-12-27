"""
Budget Module Projections - Read Models for Query Operations

Projections are built from events and provide efficient query access.
They are the "read" side of CQRS.

BudgetRegistry: Current state of all budgets (main projection)
ExpenditureLog: All expenditures for audit queries
BudgetHealthProjection: Violations and anomalies (triggers)
"""

from decimal import Decimal

from freedom_that_lasts.budget.models import BudgetStatus
from freedom_that_lasts.kernel.events import Event


class BudgetRegistry:
    """
    Main budget projection - current state of all budgets

    Built from events: BudgetCreated, BudgetActivated, AllocationAdjusted,
                       ExpenditureApproved, BudgetClosed

    Query methods: get, list_by_law, list_by_status, list_active
    """

    def __init__(self) -> None:
        self.budgets: dict[str, dict] = {}

    def apply_event(self, event: Event) -> None:
        """
        Apply an event to update the projection

        Args:
            event: Event to apply
        """
        if event.event_type == "BudgetCreated":
            self._apply_budget_created(event)
        elif event.event_type == "BudgetActivated":
            self._apply_budget_activated(event)
        elif event.event_type == "AllocationAdjusted":
            self._apply_allocation_adjusted(event)
        elif event.event_type == "ExpenditureApproved":
            self._apply_expenditure_approved(event)
        elif event.event_type == "BudgetClosed":
            self._apply_budget_closed(event)
        # Note: ExpenditureRejected is NOT applied to BudgetRegistry
        # (it goes to audit log only)

    def _apply_budget_created(self, event: Event) -> None:
        """Apply BudgetCreated event"""
        payload = event.payload
        budget_id = payload["budget_id"]

        # Build items dict
        items = {}
        for item_spec in payload["items"]:
            items[item_spec["item_id"]] = {
                "item_id": item_spec["item_id"],
                "name": item_spec["name"],
                "allocated_amount": item_spec["allocated_amount"],
                "spent_amount": "0",
                "flex_class": item_spec["flex_class"],
                "category": item_spec["category"],
            }

        # Create budget
        self.budgets[budget_id] = {
            "budget_id": budget_id,
            "law_id": payload["law_id"],
            "fiscal_year": payload["fiscal_year"],
            "items": items,
            "budget_total": payload["budget_total"],
            "status": BudgetStatus.DRAFT.value,
            "created_at": payload["created_at"],
            "activated_at": None,
            "closed_at": None,
            "metadata": payload.get("metadata", {}),
            "version": event.version,
        }

    def _apply_budget_activated(self, event: Event) -> None:
        """Apply BudgetActivated event"""
        payload = event.payload
        budget_id = payload["budget_id"]

        if budget_id in self.budgets:
            self.budgets[budget_id]["status"] = BudgetStatus.ACTIVE.value
            self.budgets[budget_id]["activated_at"] = payload["activated_at"]
            self.budgets[budget_id]["version"] = event.version

    def _apply_allocation_adjusted(self, event: Event) -> None:
        """Apply AllocationAdjusted event"""
        payload = event.payload
        budget_id = payload["budget_id"]

        if budget_id in self.budgets:
            # Update each item's allocation
            for adjustment in payload["adjustments"]:
                item_id = adjustment["item_id"]
                if item_id in self.budgets[budget_id]["items"]:
                    self.budgets[budget_id]["items"][item_id]["allocated_amount"] = (
                        adjustment["new_amount"]
                    )

            self.budgets[budget_id]["version"] = event.version

    def _apply_expenditure_approved(self, event: Event) -> None:
        """Apply ExpenditureApproved event"""
        payload = event.payload
        budget_id = payload["budget_id"]
        item_id = payload["item_id"]

        if budget_id in self.budgets:
            if item_id in self.budgets[budget_id]["items"]:
                # Increment spent amount
                current_spent = Decimal(
                    str(self.budgets[budget_id]["items"][item_id]["spent_amount"])
                )
                expenditure_amount = Decimal(str(payload["amount"]))
                new_spent = current_spent + expenditure_amount

                self.budgets[budget_id]["items"][item_id]["spent_amount"] = str(
                    new_spent
                )

            self.budgets[budget_id]["version"] = event.version

    def _apply_budget_closed(self, event: Event) -> None:
        """Apply BudgetClosed event"""
        payload = event.payload
        budget_id = payload["budget_id"]

        if budget_id in self.budgets:
            self.budgets[budget_id]["status"] = BudgetStatus.CLOSED.value
            self.budgets[budget_id]["closed_at"] = payload["closed_at"]
            self.budgets[budget_id]["version"] = event.version

    # ========== Query Methods ==========

    def get(self, budget_id: str) -> dict | None:
        """
        Get budget by ID

        Args:
            budget_id: Budget ID

        Returns:
            Budget dict or None if not found
        """
        return self.budgets.get(budget_id)

    def list_by_law(self, law_id: str) -> list[dict]:
        """
        List all budgets for a law

        Args:
            law_id: Law ID

        Returns:
            List of budget dicts
        """
        return [
            budget for budget in self.budgets.values() if budget["law_id"] == law_id
        ]

    def list_by_status(self, status: BudgetStatus) -> list[dict]:
        """
        List all budgets with given status

        Args:
            status: Budget status

        Returns:
            List of budget dicts
        """
        return [
            budget
            for budget in self.budgets.values()
            if budget["status"] == status.value
        ]

    def list_active(self) -> list[dict]:
        """
        List all ACTIVE budgets

        Returns:
            List of budget dicts
        """
        return self.list_by_status(BudgetStatus.ACTIVE)

    def list_all(self) -> list[dict]:
        """
        List all budgets

        Returns:
            List of budget dicts
        """
        return list(self.budgets.values())


class ExpenditureLog:
    """
    Expenditure audit log - all approved expenditures

    Built from events: ExpenditureApproved, ExpenditureRejected

    Query methods: get_by_budget, get_by_item, get_rejections
    """

    def __init__(self) -> None:
        self.expenditures: list[dict] = []
        self.rejections: list[dict] = []

    def apply_event(self, event: Event) -> None:
        """
        Apply an event to update the log

        Args:
            event: Event to apply
        """
        if event.event_type == "ExpenditureApproved":
            self._apply_expenditure_approved(event)
        elif event.event_type == "ExpenditureRejected":
            self._apply_expenditure_rejected(event)

    def _apply_expenditure_approved(self, event: Event) -> None:
        """Log approved expenditure"""
        payload = event.payload

        self.expenditures.append(
            {
                "expenditure_id": payload["expenditure_id"],
                "budget_id": payload["budget_id"],
                "item_id": payload["item_id"],
                "amount": payload["amount"],
                "purpose": payload["purpose"],
                "approved_at": payload["approved_at"],
                "approved_by": payload.get("approved_by"),
                "remaining_budget": payload["remaining_budget"],
                "metadata": payload.get("metadata", {}),
            }
        )

    def _apply_expenditure_rejected(self, event: Event) -> None:
        """Log rejected expenditure"""
        payload = event.payload

        self.rejections.append(
            {
                "budget_id": payload["budget_id"],
                "item_id": payload["item_id"],
                "amount": payload["amount"],
                "purpose": payload["purpose"],
                "rejected_at": payload["rejected_at"],
                "rejection_reason": payload["rejection_reason"],
                "gate_failed": payload["gate_failed"],
            }
        )

    # ========== Query Methods ==========

    def get_by_budget(self, budget_id: str) -> list[dict]:
        """
        Get all expenditures for a budget

        Args:
            budget_id: Budget ID

        Returns:
            List of expenditure dicts
        """
        return [exp for exp in self.expenditures if exp["budget_id"] == budget_id]

    def get_by_item(self, budget_id: str, item_id: str) -> list[dict]:
        """
        Get all expenditures for a budget item

        Args:
            budget_id: Budget ID
            item_id: Item ID

        Returns:
            List of expenditure dicts
        """
        return [
            exp
            for exp in self.expenditures
            if exp["budget_id"] == budget_id and exp["item_id"] == item_id
        ]

    def get_rejections(self, budget_id: str | None = None) -> list[dict]:
        """
        Get all rejected expenditures

        Args:
            budget_id: Optional budget ID to filter by

        Returns:
            List of rejection dicts
        """
        if budget_id is None:
            return self.rejections
        return [rej for rej in self.rejections if rej["budget_id"] == budget_id]


class BudgetHealthProjection:
    """
    Budget health monitoring - violations and anomalies

    Built from events: BudgetBalanceViolationDetected, BudgetOverspendDetected

    Query methods: has_violations, get_violations
    """

    def __init__(self) -> None:
        self.balance_violations: list[dict] = []
        self.overspend_incidents: list[dict] = []

    def apply_event(self, event: Event) -> None:
        """
        Apply an event to update the projection

        Args:
            event: Event to apply
        """
        if event.event_type == "BudgetBalanceViolationDetected":
            self._apply_balance_violation(event)
        elif event.event_type == "BudgetOverspendDetected":
            self._apply_overspend_detected(event)

    def _apply_balance_violation(self, event: Event) -> None:
        """Log balance violation"""
        payload = event.payload

        self.balance_violations.append(
            {
                "budget_id": payload["budget_id"],
                "detected_at": payload["detected_at"],
                "budget_total": payload["budget_total"],
                "total_allocated": payload["total_allocated"],
                "variance": payload["variance"],
                "reason": payload.get("reason", "invariant_violation"),
            }
        )

    def _apply_overspend_detected(self, event: Event) -> None:
        """Log overspend incident"""
        payload = event.payload

        self.overspend_incidents.append(
            {
                "budget_id": payload["budget_id"],
                "item_id": payload["item_id"],
                "detected_at": payload["detected_at"],
                "allocated_amount": payload["allocated_amount"],
                "spent_amount": payload["spent_amount"],
                "overspend_amount": payload["overspend_amount"],
                "reason": payload.get("reason", "concurrent_expenditure"),
            }
        )

    # ========== Query Methods ==========

    def has_violations(self, budget_id: str) -> bool:
        """
        Check if budget has any violations

        Args:
            budget_id: Budget ID

        Returns:
            True if budget has violations
        """
        balance_issues = any(
            v["budget_id"] == budget_id for v in self.balance_violations
        )
        overspend_issues = any(
            o["budget_id"] == budget_id for o in self.overspend_incidents
        )
        return balance_issues or overspend_issues

    def get_violations(self, budget_id: str | None = None) -> dict:
        """
        Get all violations

        Args:
            budget_id: Optional budget ID to filter by

        Returns:
            Dict with balance_violations and overspend_incidents
        """
        if budget_id is None:
            return {
                "balance_violations": self.balance_violations,
                "overspend_incidents": self.overspend_incidents,
            }

        return {
            "balance_violations": [
                v for v in self.balance_violations if v["budget_id"] == budget_id
            ],
            "overspend_incidents": [
                o for o in self.overspend_incidents if o["budget_id"] == budget_id
            ],
        }
