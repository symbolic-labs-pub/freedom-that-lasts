"""
TickEngine - Periodic trigger evaluation orchestrator

The TickEngine runs the automatic safeguard evaluation loop.
It's called periodically (e.g., hourly, daily) to check all
triggers and emit reflex events.

Fun fact: This is like the "heartbeat" of the immune system,
regularly checking for threats and responding automatically!
"""

from datetime import datetime

from freedom_that_lasts.feedback.indicators import compute_freedom_health
from freedom_that_lasts.feedback.triggers import evaluate_all_triggers
from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider
from freedom_that_lasts.law.events import SystemTick
from freedom_that_lasts.law.invariants import compute_in_degrees
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry


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
        return any(
            e.event_type == "DelegationConcentrationWarning"
            for e in self.triggered_events
        )

    def has_halts(self) -> bool:
        """Check if any halts were triggered"""
        return any(
            e.event_type == "DelegationConcentrationHalt" for e in self.triggered_events
        )

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
    ) -> TickResult:
        """
        Execute a single tick evaluation

        Args:
            delegation_graph: Current delegation state
            law_registry: Current law state

        Returns:
            TickResult with events and health assessment
        """
        now = self.time_provider.now()
        tick_id = generate_id()

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

        # Evaluate all triggers
        triggered_events = evaluate_all_triggers(
            in_degree_map=in_degree_map,
            overdue_laws=overdue_laws,
            policy=self.safety_policy,
            time_provider=self.time_provider,
        )

        # Append all events to store
        all_events = [tick_event] + triggered_events
        for event in all_events:
            try:
                self.event_store.append(
                    stream_id=event.stream_id,
                    expected_version=0,  # System stream is always version 0
                    events=[event],
                )
            except Exception:
                # If event already exists (idempotency), skip
                pass

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

        return count
