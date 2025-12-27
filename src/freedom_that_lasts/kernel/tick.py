"""
TickEngine - Periodic trigger evaluation orchestrator

The TickEngine runs the automatic safeguard evaluation loop.
It's called periodically (e.g., hourly, daily) to check all
triggers and emit reflex events.

Fun fact: This is like the "heartbeat" of the immune system,
regularly checking for threats and responding automatically!
"""

from datetime import datetime

from freedom_that_lasts.budget.projections import BudgetRegistry
from freedom_that_lasts.budget.triggers import (
    evaluate_budget_balance_trigger,
    evaluate_expenditure_overspend_trigger,
)
from freedom_that_lasts.feedback.indicators import compute_freedom_health
from freedom_that_lasts.feedback.triggers import evaluate_all_triggers
from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.logging import LogOperation, get_logger
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider
from freedom_that_lasts.law.events import SystemTick
from freedom_that_lasts.law.invariants import compute_in_degrees
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry
from freedom_that_lasts.resource.triggers import evaluate_all_procurement_triggers

logger = get_logger(__name__)


class TickResult:
    """
    Result of a tick evaluation

    Contains all events generated and health assessment.
    """

    def __init__(
        self,
        tick_id: str,
        tick_at: datetime,
        triggered_events: list[Event],
        freedom_health: any,  # FreedomHealthScore
    ):
        self.tick_id = tick_id
        self.tick_at = tick_at
        self.triggered_events = triggered_events
        self.freedom_health = freedom_health

    def has_warnings(self) -> bool:
        """Check if any warnings were triggered"""
        warning_types = {
            "DelegationConcentrationWarning",
            "BudgetBalanceViolationDetected",
            "BudgetOverspendDetected",
            "EmptyFeasibleSetDetected",
            "SupplierConcentrationWarning",
        }
        return any(e.event_type in warning_types for e in self.triggered_events)

    def has_halts(self) -> bool:
        """Check if any halts were triggered"""
        halt_types = {
            "DelegationConcentrationHalt",
            "SupplierConcentrationHalt",
        }
        return any(e.event_type in halt_types for e in self.triggered_events)

    def summary(self) -> str:
        """Human-readable summary of tick result"""
        parts = [
            f"Tick {self.tick_id} at {self.tick_at}",
            f"Risk Level: {self.freedom_health.risk_level.value}",
            f"Events: {len(self.triggered_events)}",
        ]

        if self.has_halts():
            parts.append("⚠️  HALT conditions detected!")
        elif self.has_warnings():
            parts.append("⚠️  Warning conditions detected")

        return " | ".join(parts)


class TickEngine:
    """
    Orchestrates periodic trigger evaluation

    The TickEngine:
    1. Loads current state (projections)
    2. Evaluates all triggers
    3. Emits SystemTick event
    4. Emits any triggered reflex events
    5. Computes FreedomHealth scorecard
    6. Returns summary result
    """

    def __init__(
        self,
        event_store: SQLiteEventStore,
        time_provider: TimeProvider,
        safety_policy: SafetyPolicy,
    ):
        self.event_store = event_store
        self.time_provider = time_provider
        self.safety_policy = safety_policy

    def tick(
        self,
        delegation_graph: DelegationGraph,
        law_registry: LawRegistry,
        budget_registry: BudgetRegistry | None = None,
        supplier_registry: any = None,  # SupplierRegistry
        tender_registry: any = None,  # TenderRegistry
    ) -> TickResult:
        """
        Execute a single tick evaluation

        Args:
            delegation_graph: Current delegation state
            law_registry: Current law state
            budget_registry: Optional budget state (for budget triggers)
            supplier_registry: Optional supplier registry (for procurement triggers)
            tender_registry: Optional tender registry (for procurement triggers)

        Returns:
            TickResult with events and health assessment
        """
        now = self.time_provider.now()
        tick_id = generate_id()

        with LogOperation(
            logger,
            "tick_evaluation",
            tick_id=tick_id,
            has_budget_registry=budget_registry is not None,
            has_procurement_registries=(
                supplier_registry is not None and tender_registry is not None
            ),
        ):
            # Emit SystemTick event
            tick_event = Event(
                event_id=generate_id(),
                stream_id="system",
                stream_type="feedback",
                version=1,
                command_id=generate_id(),
                event_type="SystemTick",
                occurred_at=now,
                actor_id="system",
                payload=SystemTick(tick_at=now, tick_id=tick_id).model_dump(mode="json"),
            )

            # Compute current state for triggers
            active_edges = delegation_graph.get_active_edges(now)
            in_degree_map = compute_in_degrees(active_edges, now)
            overdue_laws = law_registry.list_overdue_reviews(now)

            logger.debug(
                "Computed governance state",
                tick_id=tick_id,
                active_edges_count=len(active_edges),
                unique_actors=len(in_degree_map),
                overdue_laws_count=len(overdue_laws),
            )

            # Evaluate law/delegation triggers
            triggered_events = evaluate_all_triggers(
                in_degree_map=in_degree_map,
                overdue_laws=overdue_laws,
                policy=self.safety_policy,
                time_provider=self.time_provider,
            )

            logger.debug(
                "Evaluated law/delegation triggers",
                tick_id=tick_id,
                triggered_count=len(triggered_events),
                event_types=[e.event_type for e in triggered_events],
            )

            # Evaluate budget triggers if budget registry is provided
            if budget_registry is not None:
                active_budgets = budget_registry.list_active()
                logger.debug(
                    "Evaluating budget triggers",
                    tick_id=tick_id,
                    active_budgets_count=len(active_budgets),
                )

                # Check budget balance constraints
                balance_events = evaluate_budget_balance_trigger(active_budgets, now)
                triggered_events.extend(balance_events)

                # Check expenditure overspending
                overspend_events = evaluate_expenditure_overspend_trigger(
                    active_budgets, now
                )
                triggered_events.extend(overspend_events)

                logger.debug(
                    "Budget triggers evaluated",
                    tick_id=tick_id,
                    balance_events_count=len(balance_events),
                    overspend_events_count=len(overspend_events),
                )

            # Evaluate procurement triggers if registries are provided
            if supplier_registry is not None and tender_registry is not None:
                supplier_dict = supplier_registry.to_dict()
                tender_dict = tender_registry.to_dict()

                logger.debug(
                    "Evaluating procurement triggers",
                    tick_id=tick_id,
                    suppliers_count=len(supplier_dict),
                    tenders_count=len(tender_dict),
                )

                procurement_events = evaluate_all_procurement_triggers(
                    supplier_registry=supplier_dict,
                    tender_registry=tender_dict,
                    safety_policy=self.safety_policy,
                    now=now,
                )
                triggered_events.extend(procurement_events)

                logger.debug(
                    "Procurement triggers evaluated",
                    tick_id=tick_id,
                    procurement_events_count=len(procurement_events),
                )

            # Append all events to store
            all_events = [tick_event] + triggered_events
            events_appended = 0
            events_skipped = 0

            for event in all_events:
                try:
                    self.event_store.append(
                        stream_id=event.stream_id,
                        expected_version=0,  # System stream is always version 0
                        events=[event],
                    )
                    events_appended += 1
                except Exception as e:
                    # If event already exists (idempotency), skip
                    events_skipped += 1
                    logger.debug(
                        "Event append skipped (idempotency)",
                        tick_id=tick_id,
                        event_type=event.event_type,
                        error=str(e),
                    )

            logger.debug(
                "Events appended to store",
                tick_id=tick_id,
                appended=events_appended,
                skipped=events_skipped,
                total=len(all_events),
            )

            # Compute FreedomHealth scorecard
            active_laws = law_registry.list_active()
            upcoming_7d_count = self._count_upcoming_reviews(law_registry, now, 7)
            upcoming_30d_count = self._count_upcoming_reviews(law_registry, now, 30)

            freedom_health = compute_freedom_health(
                in_degree_map=in_degree_map,
                total_active_laws=len(active_laws),
                overdue_reviews=len(overdue_laws),
                upcoming_7d=upcoming_7d_count,
                upcoming_30d=upcoming_30d_count,
                policy=self.safety_policy,
                now=now,
            )

            logger.info(
                "Tick evaluation completed",
                tick_id=tick_id,
                risk_level=freedom_health.risk_level.value,
                triggered_events_count=len(triggered_events),
                gini_coefficient=freedom_health.concentration.gini_coefficient,
                overdue_laws=len(overdue_laws),
                has_warnings=any(
                    e.event_type
                    in {
                        "DelegationConcentrationWarning",
                        "BudgetBalanceViolationDetected",
                        "BudgetOverspendDetected",
                        "EmptyFeasibleSetDetected",
                        "SupplierConcentrationWarning",
                    }
                    for e in triggered_events
                ),
                has_halts=any(
                    e.event_type
                    in {
                        "DelegationConcentrationHalt",
                        "SupplierConcentrationHalt",
                    }
                    for e in triggered_events
                ),
            )

            return TickResult(
                tick_id=tick_id,
                tick_at=now,
                triggered_events=triggered_events,
                freedom_health=freedom_health,
            )

    def _count_upcoming_reviews(
        self, law_registry: LawRegistry, now: datetime, days: int
    ) -> int:
        """Count laws with reviews due in next N days"""
        from datetime import timedelta

        future = now + timedelta(days=days)
        count = 0

        for law in law_registry.list_active():
            if law.get("next_checkpoint_at"):
                checkpoint_dt = (
                    datetime.fromisoformat(law["next_checkpoint_at"])
                    if isinstance(law["next_checkpoint_at"], str)
                    else law["next_checkpoint_at"]
                )
                if now < checkpoint_dt <= future:
                    count += 1

        logger.debug(
            "Counted upcoming reviews",
            days=days,
            count=count,
            total_active_laws=len(law_registry.list_active()),
        )

        return count
