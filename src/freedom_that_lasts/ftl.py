"""
FTL - Main façade class

This is the primary interface for interacting with the Freedom That Lasts system.
It provides a clean, high-level API that hides the complexity of event sourcing,
projections, and command handling.

Example:
    >>> from freedom_that_lasts import FTL
    >>> ftl = FTL("governance.db")
    >>> workspace = ftl.create_workspace("Health Services")
    >>> ftl.delegate("alice", workspace.workspace_id, "bob", ttl_days=180)
    >>> law = ftl.create_law(workspace.workspace_id, "Primary Care Pilot", ...)
    >>> ftl.activate_law(law.law_id)
    >>> ftl.tick()  # Run trigger evaluation
    >>> health = ftl.health()  # Get system health
"""

from datetime import datetime
from pathlib import Path
from typing import Any

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
from freedom_that_lasts.budget.projections import (
    BudgetHealthProjection,
    BudgetRegistry,
    ExpenditureLog,
)
from freedom_that_lasts.feedback.indicators import compute_freedom_health
from freedom_that_lasts.feedback.models import FreedomHealthScore
from freedom_that_lasts.feedback.projections import FreedomHealthProjection, SafetyEventLog
from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.tick import TickEngine, TickResult
from freedom_that_lasts.kernel.time import RealTimeProvider, TimeProvider
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    AdjustLaw,
    ArchiveLaw,
    CompleteLawReview,
    CreateLaw,
    CreateWorkspace,
    DelegateDecisionRight,
    ScheduleLawSunset,
    TriggerLawReview,
)
from freedom_that_lasts.law.handlers import LawCommandHandlers
from freedom_that_lasts.law.invariants import compute_in_degrees
from freedom_that_lasts.law.models import ReversibilityClass
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry, WorkspaceRegistry


class FTL:
    """
    Freedom That Lasts main façade

    Provides a unified API for all system operations including:
    - Workspace management
    - Delegation of decision rights
    - Law lifecycle management
    - Automatic safeguard triggers
    - Health monitoring
    """

    def __init__(
        self,
        sqlite_path: str | Path,
        safety_policy: SafetyPolicy | None = None,
        time_provider: TimeProvider | None = None,
    ) -> None:
        """
        Initialize FTL system

        Args:
            sqlite_path: Path to SQLite database
            safety_policy: Safety policy (uses defaults if None)
            time_provider: Time provider (uses real time if None)
        """
        self.sqlite_path = Path(sqlite_path)
        self.safety_policy = safety_policy or SafetyPolicy()
        self.time_provider = time_provider or RealTimeProvider()

        # Initialize infrastructure
        self.event_store = SQLiteEventStore(str(self.sqlite_path))
        self.law_handlers = LawCommandHandlers(self.time_provider, self.safety_policy)
        self.budget_handlers = BudgetCommandHandlers(
            self.time_provider, self.safety_policy
        )
        self.tick_engine = TickEngine(
            self.event_store, self.time_provider, self.safety_policy
        )

        # Initialize projections
        self.workspace_registry = WorkspaceRegistry()
        self.delegation_graph = DelegationGraph()
        self.law_registry = LawRegistry()
        self.budget_registry = BudgetRegistry()
        self.expenditure_log = ExpenditureLog()
        self.budget_health_projection = BudgetHealthProjection()
        self.freedom_health_projection = FreedomHealthProjection()
        self.safety_event_log = SafetyEventLog()

        # Rebuild projections from event store
        self._rebuild_projections()

    def _rebuild_projections(self) -> None:
        """Rebuild all projections from event store"""
        all_events = self.event_store.load_all_events()
        for event in all_events:
            # Apply to appropriate projections
            if event.event_type in ["WorkspaceCreated", "WorkspaceArchived"]:
                self.workspace_registry.apply_event(event)
            elif event.event_type in [
                "DecisionRightDelegated",
                "DelegationRevoked",
                "DelegationExpired",
                "DelegationRenewed",
            ]:
                self.delegation_graph.apply_event(event)
            elif event.event_type.startswith("Law"):
                self.law_registry.apply_event(event)
            elif event.event_type.startswith("Budget") or event.event_type.startswith(
                "Expenditure"
            ):
                self.budget_registry.apply_event(event)
                self.expenditure_log.apply_event(event)
                self.budget_health_projection.apply_event(event)
            elif event.event_type in [
                "DelegationConcentrationWarning",
                "DelegationConcentrationHalt",
                "TransparencyEscalated",
                "LawReviewTriggered",
                "SystemTick",
            ]:
                self.safety_event_log.apply_event(event)

    # Workspace operations

    def create_workspace(
        self, name: str, scope: dict[str, Any] | None = None, actor_id: str = "system"
    ) -> dict[str, Any]:
        """
        Create a new workspace

        Args:
            name: Workspace name
            scope: Workspace scope (territory, domain, etc.)
            actor_id: Actor creating the workspace

        Returns:
            Workspace dict with workspace_id
        """
        command = CreateWorkspace(
            name=name, parent_workspace_id=None, scope=scope or {}
        )
        events = self.law_handlers.handle_create_workspace(
            command, generate_id(), actor_id
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.workspace_registry.apply_event(event)

        return self.workspace_registry.get(events[0].payload["workspace_id"])

    def list_workspaces(self) -> list[dict[str, Any]]:
        """List all active workspaces"""
        return self.workspace_registry.list_active()

    # Delegation operations

    def delegate(
        self,
        from_actor: str,
        workspace_id: str,
        to_actor: str,
        ttl_days: int,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Delegate decision rights

        Args:
            from_actor: Delegating actor
            workspace_id: Workspace scope
            to_actor: Receiving actor
            ttl_days: Time-to-live in days
            actor_id: Actor executing delegation (defaults to from_actor)

        Returns:
            Delegation dict
        """
        command = DelegateDecisionRight(
            from_actor=from_actor,
            workspace_id=workspace_id,
            to_actor=to_actor,
            ttl_days=ttl_days,
        )
        events = self.law_handlers.handle_delegate_decision_right(
            command,
            generate_id(),
            actor_id or from_actor,
            self.workspace_registry.to_dict()["workspaces"],
            self.delegation_graph.get_active_edges(self.time_provider.now()),
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.delegation_graph.apply_event(event)

        return self.delegation_graph.get(events[0].payload["delegation_id"])

    # Law operations

    def create_law(
        self,
        workspace_id: str,
        title: str,
        scope: dict[str, Any],
        reversibility_class: str | ReversibilityClass,
        checkpoints: list[int],
        params: dict[str, Any] | None = None,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """
        Create a new law

        Args:
            workspace_id: Parent workspace
            title: Law title
            scope: Law scope
            reversibility_class: REVERSIBLE, SEMI_REVERSIBLE, or IRREVERSIBLE
            checkpoints: Review checkpoint schedule (days)
            params: Law parameters
            actor_id: Actor creating the law

        Returns:
            Law dict with law_id
        """
        if isinstance(reversibility_class, str):
            reversibility_class = ReversibilityClass(reversibility_class)

        command = CreateLaw(
            workspace_id=workspace_id,
            title=title,
            scope=scope,
            reversibility_class=reversibility_class,
            checkpoints=checkpoints,
            params=params or {},
        )
        events = self.law_handlers.handle_create_law(
            command,
            generate_id(),
            actor_id,
            self.workspace_registry.to_dict()["workspaces"],
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.law_registry.apply_event(event)

        return self.law_registry.get(events[0].payload["law_id"])

    def activate_law(self, law_id: str, actor_id: str = "system") -> dict[str, Any]:
        """
        Activate a law (DRAFT → ACTIVE)

        Args:
            law_id: Law to activate
            actor_id: Actor activating the law

        Returns:
            Updated law dict
        """
        command = ActivateLaw(law_id=law_id)
        law = self.law_registry.get(law_id)
        current_version = law["version"] if law else 0

        events = self.law_handlers.handle_activate_law(
            command, generate_id(), actor_id, self.law_registry.to_dict()["laws"]
        )

        # Store events and update projections
        for event in events:
            self.event_store.append(event.stream_id, current_version, [event])
            self.law_registry.apply_event(event)

        return self.law_registry.get(law_id)

    def complete_review(
        self,
        law_id: str,
        outcome: str,
        notes: str,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """
        Complete a law review

        Args:
            law_id: Law being reviewed
            outcome: "continue", "adjust", or "sunset"
            notes: Review notes
            actor_id: Actor completing review

        Returns:
            Updated law dict
        """
        command = CompleteLawReview(law_id=law_id, outcome=outcome, notes=notes)
        law = self.law_registry.get(law_id)
        current_version = law["version"] if law else 0

        events = self.law_handlers.handle_complete_law_review(
            command, generate_id(), actor_id, self.law_registry.to_dict()["laws"]
        )

        # Store events and update projections
        for event in events:
            self.event_store.append(event.stream_id, current_version, [event])
            self.law_registry.apply_event(event)
            current_version = event.version

        return self.law_registry.get(law_id)

    def list_laws(self, status: str | None = None) -> list[dict[str, Any]]:
        """
        List laws

        Args:
            status: Filter by status (DRAFT, ACTIVE, REVIEW, SUNSET, ARCHIVED)

        Returns:
            List of law dicts
        """
        if status:
            from freedom_that_lasts.law.models import LawStatus

            return self.law_registry.list_by_status(LawStatus(status))
        return list(self.law_registry.laws.values())

    # Monitoring operations

    def tick(self) -> TickResult:
        """
        Run trigger evaluation loop

        Evaluates all automatic safeguards and emits reflex events.

        Returns:
            TickResult with triggered events and health assessment
        """
        result = self.tick_engine.tick(self.delegation_graph, self.law_registry)

        # Store and apply triggered events
        for event in result.triggered_events:
            # Store in event store
            try:
                current_version = 0
                if event.stream_type == "law":
                    law = self.law_registry.get(event.stream_id)
                    current_version = law["version"] if law else 0
                self.event_store.append(event.stream_id, current_version, [event])
            except Exception:
                # Event might already exist (idempotency)
                pass

            # Apply to projections
            self.law_registry.apply_event(event)
            self.safety_event_log.apply_event(event)

        # Update health projection
        self.freedom_health_projection.update_health(result.freedom_health)

        return result

    def health(self) -> FreedomHealthScore:
        """
        Get current system health

        Returns:
            FreedomHealthScore with risk level and metrics
        """
        # Compute fresh health assessment
        now = self.time_provider.now()
        active_edges = self.delegation_graph.get_active_edges(now)
        in_degree_map = compute_in_degrees(active_edges, now)
        overdue_laws = self.law_registry.list_overdue_reviews(now)
        active_laws = self.law_registry.list_active()

        # Count upcoming reviews
        from datetime import timedelta

        upcoming_7d = 0
        upcoming_30d = 0
        for law in active_laws:
            if law.get("next_checkpoint_at"):
                checkpoint_dt = (
                    datetime.fromisoformat(law["next_checkpoint_at"])
                    if isinstance(law["next_checkpoint_at"], str)
                    else law["next_checkpoint_at"]
                )
                if now < checkpoint_dt <= now + timedelta(days=7):
                    upcoming_7d += 1
                if now < checkpoint_dt <= now + timedelta(days=30):
                    upcoming_30d += 1

        return compute_freedom_health(
            in_degree_map=in_degree_map,
            total_active_laws=len(active_laws),
            overdue_reviews=len(overdue_laws),
            upcoming_7d=upcoming_7d,
            upcoming_30d=upcoming_30d,
            policy=self.safety_policy,
            now=now,
        )

    def get_safety_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get recent safety events (warnings, halts, escalations)

        Args:
            limit: Maximum events to return

        Returns:
            List of safety event dicts
        """
        return self.safety_event_log.get_recent(limit=limit)

    def get_safety_policy(self) -> SafetyPolicy:
        """Get current safety policy"""
        return self.safety_policy

    # Budget operations

    def create_budget(
        self,
        law_id: str,
        fiscal_year: int,
        items: list[dict[str, Any]],
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """
        Create a new budget for a law

        Args:
            law_id: Law ID this budget is for
            fiscal_year: Fiscal year (e.g., 2025)
            items: Budget items [{name, allocated_amount, flex_class, category}, ...]
            actor_id: Actor creating the budget

        Returns:
            Budget dict with budget_id

        Raises:
            LawNotFoundForBudget: If law doesn't exist
        """
        # Convert items to BudgetItemSpec
        item_specs = [
            BudgetItemSpec(
                name=item["name"],
                allocated_amount=item["allocated_amount"],
                flex_class=item["flex_class"],
                category=item.get("category", "general"),
            )
            for item in items
        ]

        command = CreateBudget(
            law_id=law_id, fiscal_year=fiscal_year, items=item_specs
        )

        events = self.budget_handlers.handle_create_budget(
            command,
            generate_id(),
            actor_id,
            self.law_registry.to_dict()["laws"],
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.budget_registry.apply_event(event)

        return self.budget_registry.get(events[0].payload["budget_id"])

    def activate_budget(
        self, budget_id: str, actor_id: str = "system"
    ) -> dict[str, Any]:
        """
        Activate a budget (DRAFT → ACTIVE)

        Only ACTIVE budgets can approve expenditures.

        Args:
            budget_id: Budget ID
            actor_id: Actor activating the budget

        Returns:
            Updated budget dict

        Raises:
            BudgetNotFound: If budget doesn't exist
        """
        command = ActivateBudget(budget_id=budget_id)

        events = self.budget_handlers.handle_activate_budget(
            command,
            generate_id(),
            actor_id,
            self.budget_registry.budgets,
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.budget_registry.apply_event(event)

        return self.budget_registry.get(budget_id)

    def adjust_allocation(
        self,
        budget_id: str,
        adjustments: list[dict[str, Any]],
        reason: str,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """
        Adjust budget allocations with multi-gate enforcement

        ALL four gates must pass:
        - Gate 1: Step-size limits (flex class constraints)
        - Gate 2: Budget balance (zero-sum, strict)
        - Gate 3: Delegation authority (checked by façade)
        - Gate 4: No overspending (allocation >= current spending)

        Args:
            budget_id: Budget ID
            adjustments: [{item_id, change_amount}, ...]
            reason: Reason for adjustment
            actor_id: Actor making the adjustment

        Returns:
            Updated budget dict

        Raises:
            BudgetNotFound: If budget doesn't exist
            FlexStepSizeViolation: If any adjustment exceeds flex class limit
            BudgetBalanceViolation: If adjustments break zero-sum
            AllocationBelowSpending: If adjustment creates overspending
        """
        # Convert adjustments to AdjustmentSpec
        adjustment_specs = [
            AdjustmentSpec(
                item_id=adj["item_id"], change_amount=adj["change_amount"]
            )
            for adj in adjustments
        ]

        command = AdjustAllocation(
            budget_id=budget_id, adjustments=adjustment_specs, reason=reason
        )

        events = self.budget_handlers.handle_adjust_allocation(
            command,
            generate_id(),
            actor_id,
            self.budget_registry.budgets,
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.budget_registry.apply_event(event)

        return self.budget_registry.get(budget_id)

    def approve_expenditure(
        self,
        budget_id: str,
        item_id: str,
        amount: Any,
        purpose: str,
        actor_id: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Approve an expenditure against a budget item

        Returns approval or rejection event depending on validation.

        Args:
            budget_id: Budget ID
            item_id: Budget item ID
            amount: Expenditure amount (Decimal or str/int)
            purpose: Purpose of expenditure
            actor_id: Actor approving the expenditure
            metadata: Optional metadata

        Returns:
            Budget dict (updated if approved)
        """
        command = ApproveExpenditure(
            budget_id=budget_id,
            item_id=item_id,
            amount=amount,
            purpose=purpose,
            metadata=metadata or {},
        )

        events = self.budget_handlers.handle_approve_expenditure(
            command,
            generate_id(),
            actor_id,
            self.budget_registry.budgets,
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.budget_registry.apply_event(event)
            self.expenditure_log.apply_event(event)

        return self.budget_registry.get(budget_id)

    def close_budget(
        self, budget_id: str, reason: str, actor_id: str = "system"
    ) -> dict[str, Any]:
        """
        Close a budget (end of fiscal year)

        No further expenditures or adjustments allowed after closure.

        Args:
            budget_id: Budget ID
            reason: Reason for closure
            actor_id: Actor closing the budget

        Returns:
            Closed budget dict

        Raises:
            BudgetNotFound: If budget doesn't exist
        """
        command = CloseBudget(budget_id=budget_id, reason=reason)

        events = self.budget_handlers.handle_close_budget(
            command,
            generate_id(),
            actor_id,
            self.budget_registry.budgets,
        )

        # Store events and update projections
        for event in events:
            expected_version = event.version - 1
            self.event_store.append(event.stream_id, expected_version, [event])
            self.budget_registry.apply_event(event)

        return self.budget_registry.get(budget_id)

    def list_budgets(
        self, law_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """
        List budgets

        Args:
            law_id: Optional law ID to filter by
            status: Optional status to filter by (DRAFT, ACTIVE, CLOSED)

        Returns:
            List of budget dicts
        """
        if law_id:
            return self.budget_registry.list_by_law(law_id)
        elif status:
            from freedom_that_lasts.budget.models import BudgetStatus

            return self.budget_registry.list_by_status(BudgetStatus(status))
        else:
            return self.budget_registry.list_all()

    def get_expenditures(
        self, budget_id: str, item_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get expenditure history for a budget or budget item

        Args:
            budget_id: Budget ID
            item_id: Optional item ID to filter by

        Returns:
            List of expenditure dicts
        """
        if item_id:
            return self.expenditure_log.get_by_item(budget_id, item_id)
        else:
            return self.expenditure_log.get_by_budget(budget_id)
