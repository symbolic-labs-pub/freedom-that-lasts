"""
End-to-End Integration Tests - Complete System Workflows

These tests verify that all components work together correctly:
- Commands → Events → Event Store → Projections → Triggers → Health
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.feedback.indicators import compute_freedom_health
from freedom_that_lasts.feedback.models import RiskLevel
from freedom_that_lasts.feedback.projections import FreedomHealthProjection, SafetyEventLog
from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.kernel.tick import TickEngine
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    CreateLaw,
    CreateWorkspace,
    DelegateDecisionRight,
)
from freedom_that_lasts.law.handlers import LawCommandHandlers
from freedom_that_lasts.law.invariants import compute_in_degrees
from freedom_that_lasts.law.models import ReversibilityClass
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry, WorkspaceRegistry


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide deterministic time"""
    return TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def event_store(tmp_path) -> SQLiteEventStore:
    """Provide event store"""
    db_path = tmp_path / "test_e2e.db"
    return SQLiteEventStore(str(db_path))


@pytest.fixture
def safety_policy() -> SafetyPolicy:
    """Provide safety policy with reasonable thresholds"""
    return SafetyPolicy(
        delegation_gini_warn=0.5,
        delegation_gini_halt=0.7,
        delegation_in_degree_warn=50,
        delegation_in_degree_halt=100,
    )


@pytest.fixture
def handlers(test_time: TestTimeProvider, safety_policy: SafetyPolicy) -> LawCommandHandlers:
    """Provide command handlers"""
    return LawCommandHandlers(test_time, safety_policy)


def test_complete_governance_workflow(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """
    Test complete governance workflow end-to-end:

    1. Create workspace
    2. Delegate decision rights (healthy distribution)
    3. Create and activate law
    4. Run tick → healthy system (GREEN)
    5. Advance time past checkpoint
    6. Run tick → triggers review automatically
    """
    # Initialize projections
    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()
    freedom_health_projection = FreedomHealthProjection()
    safety_event_log = SafetyEventLog()
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    # Step 1: Create workspace
    create_ws = CreateWorkspace(name="Health Services", scope={"territory": "Budapest"})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")

    for event in ws_events:
        workspace_registry.apply_event(event)
        event_store.append(event.stream_id, 0, [event])

    workspace_id = ws_events[0].payload["workspace_id"]
    assert len(workspace_registry.list_active()) == 1

    # Step 2: Delegate decision rights (healthy distribution)
    for to_actor in ["bob", "charlie", "dave"]:
        delegate_cmd = DelegateDecisionRight(
            from_actor="alice",
            workspace_id=workspace_id,
            to_actor=to_actor,
            ttl_days=180,
        )
        del_events = handlers.handle_delegate_decision_right(
            delegate_cmd,
            generate_id(),
            "alice",
            workspace_registry.to_dict()["workspaces"],
            delegation_graph.get_active_edges(test_time.now()),
        )
        for event in del_events:
            delegation_graph.apply_event(event)
            event_store.append(event.stream_id, 0, [event])

    # Verify delegation state
    active_edges = delegation_graph.get_active_edges(test_time.now())
    assert len(active_edges) == 3

    # Step 3: Create law
    create_law = CreateLaw(
        workspace_id=workspace_id,
        title="Primary Care Access Pilot",
        scope={"territory": "District5"},
        reversibility_class=ReversibilityClass.SEMI_REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={"max_wait_days": 10},
    )
    law_events = handlers.handle_create_law(
        create_law,
        generate_id(),
        "alice",
        workspace_registry.to_dict()["workspaces"],
    )
    for event in law_events:
        law_registry.apply_event(event)
        event_store.append(event.stream_id, 0, [event])

    law_id = law_events[0].payload["law_id"]
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "DRAFT"

    # Step 4: Activate law
    activate = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in activate_events:
        law_registry.apply_event(event)
        # Increment version for stream
        current_version = law_registry.get(law_id)["version"] - 1
        event_store.append(event.stream_id, current_version, [event])

    law = law_registry.get(law_id)
    assert law["status"] == "ACTIVE"
    assert law["next_checkpoint_at"] is not None

    # Step 5: Run tick → should be healthy (GREEN)
    tick_result = tick_engine.tick(delegation_graph, law_registry)

    assert tick_result.freedom_health.risk_level == RiskLevel.GREEN
    assert not tick_result.has_warnings()
    assert not tick_result.has_halts()

    # Update projection
    freedom_health_projection.update_health(tick_result.freedom_health)

    # Step 6: Advance time past checkpoint (35 days)
    test_time.advance_days(35)

    # Step 7: Run tick → should trigger review automatically
    tick_result = tick_engine.tick(delegation_graph, law_registry)

    # Should trigger law review
    review_events = [
        e for e in tick_result.triggered_events if e.event_type == "LawReviewTriggered"
    ]
    assert len(review_events) == 1
    assert review_events[0].payload["law_id"] == law_id

    # Apply review event to projection
    for event in tick_result.triggered_events:
        law_registry.apply_event(event)
        safety_event_log.apply_event(event)

    # Verify law is now in REVIEW status
    law = law_registry.get(law_id)
    assert law["status"] == "REVIEW"

    # Verify safety event log tracked the trigger
    recent_events = safety_event_log.get_recent(limit=10)
    assert len(recent_events) > 0
    assert any(e["event_type"] == "LawReviewTriggered" for e in recent_events)


def test_concentration_warning_workflow(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """
    Test concentration warning workflow:

    1. Create workspace
    2. Create concentrated delegations (triggers warning)
    3. Run tick → emits warning event
    4. Verify health = YELLOW
    5. Verify warning logged
    """
    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()
    safety_event_log = SafetyEventLog()
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    # Create workspace
    create_ws = CreateWorkspace(name="Test", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create concentrated delegations (unequal distribution)
    # bob: 35, charlie: 3, dave: 2 → Gini ~0.54 > 0.5
    for i in range(35):
        delegate_cmd = DelegateDecisionRight(
            from_actor=f"actor-{i}",
            workspace_id=workspace_id,
            to_actor="bob",
            ttl_days=180,
        )
        del_events = handlers.handle_delegate_decision_right(
            delegate_cmd,
            generate_id(),
            f"actor-{i}",
            workspace_registry.to_dict()["workspaces"],
            delegation_graph.get_active_edges(test_time.now()),
        )
        for event in del_events:
            delegation_graph.apply_event(event)

    # Add some to charlie and dave
    for to_actor, count in [("charlie", 3), ("dave", 2)]:
        for i in range(count):
            delegate_cmd = DelegateDecisionRight(
                from_actor=f"delegator-{to_actor}-{i}",
                workspace_id=workspace_id,
                to_actor=to_actor,
                ttl_days=180,
            )
            del_events = handlers.handle_delegate_decision_right(
                delegate_cmd,
                generate_id(),
                f"delegator-{to_actor}-{i}",
                workspace_registry.to_dict()["workspaces"],
                delegation_graph.get_active_edges(test_time.now()),
            )
            for event in del_events:
                delegation_graph.apply_event(event)

    # Run tick
    tick_result = tick_engine.tick(delegation_graph, law_registry)

    # Should emit concentration warning
    assert tick_result.freedom_health.risk_level == RiskLevel.YELLOW
    assert tick_result.has_warnings()
    assert not tick_result.has_halts()

    warning_events = [
        e for e in tick_result.triggered_events
        if e.event_type == "DelegationConcentrationWarning"
    ]
    assert len(warning_events) == 1

    # Apply to safety log
    for event in tick_result.triggered_events:
        safety_event_log.apply_event(event)

    # Verify logged
    warnings = safety_event_log.get_by_type("DelegationConcentrationWarning")
    assert len(warnings) == 1


def test_concentration_halt_with_escalation(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """
    Test concentration halt with automatic transparency escalation:

    1. Create extreme concentration (triggers halt)
    2. Run tick → emits halt + transparency escalation
    3. Verify health = RED
    4. Verify automatic responses engaged
    """
    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()
    safety_event_log = SafetyEventLog()
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    # Create workspace
    create_ws = CreateWorkspace(name="Test", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create extreme concentration (triggers halt via in-degree)
    for i in range(120):  # Above halt threshold of 100
        delegate_cmd = DelegateDecisionRight(
            from_actor=f"actor-{i}",
            workspace_id=workspace_id,
            to_actor="bob",
            ttl_days=180,
        )
        del_events = handlers.handle_delegate_decision_right(
            delegate_cmd,
            generate_id(),
            f"actor-{i}",
            workspace_registry.to_dict()["workspaces"],
            delegation_graph.get_active_edges(test_time.now()),
        )
        for event in del_events:
            delegation_graph.apply_event(event)

    # Run tick
    tick_result = tick_engine.tick(delegation_graph, law_registry)

    # Should emit halt + transparency escalation
    assert tick_result.freedom_health.risk_level == RiskLevel.RED
    assert tick_result.has_halts()

    halt_events = [
        e for e in tick_result.triggered_events
        if e.event_type == "DelegationConcentrationHalt"
    ]
    transparency_events = [
        e for e in tick_result.triggered_events if e.event_type == "TransparencyEscalated"
    ]

    assert len(halt_events) == 1
    assert len(transparency_events) == 1

    # Verify automatic responses
    halt_payload = halt_events[0].payload
    assert "transparency_escalated" in halt_payload["automatic_responses"]

    # Apply to safety log
    for event in tick_result.triggered_events:
        safety_event_log.apply_event(event)

    # Verify all events logged
    event_counts = safety_event_log.count_by_type()
    assert event_counts.get("DelegationConcentrationHalt", 0) == 1
    assert event_counts.get("TransparencyEscalated", 0) == 1


def test_projection_rebuild_from_events(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """
    Test that projections can be rebuilt from events:

    1. Create workspace, delegations, laws
    2. Store all events
    3. Build new projection from scratch
    4. Verify same state
    """
    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Create workspace
    create_ws = CreateWorkspace(name="Rebuild Test", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
        event_store.append(event.stream_id, 0, [event])
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create delegations
    for to_actor in ["bob", "charlie"]:
        delegate_cmd = DelegateDecisionRight(
            from_actor="alice",
            workspace_id=workspace_id,
            to_actor=to_actor,
            ttl_days=180,
        )
        del_events = handlers.handle_delegate_decision_right(
            delegate_cmd,
            generate_id(),
            "alice",
            workspace_registry.to_dict()["workspaces"],
            delegation_graph.get_active_edges(test_time.now()),
        )
        for event in del_events:
            delegation_graph.apply_event(event)
            event_store.append(event.stream_id, 0, [event])

    # Create law
    create_law = CreateLaw(
        workspace_id=workspace_id,
        title="Test Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={},
    )
    law_events = handlers.handle_create_law(
        create_law, generate_id(), "alice", workspace_registry.to_dict()["workspaces"]
    )
    for event in law_events:
        law_registry.apply_event(event)
        event_store.append(event.stream_id, 0, [event])
    law_id = law_events[0].payload["law_id"]

    # Now rebuild projections from event store
    rebuilt_workspace_registry = WorkspaceRegistry()
    rebuilt_delegation_graph = DelegationGraph()
    rebuilt_law_registry = LawRegistry()

    # Get all events and replay
    all_events = event_store.load_all_events()
    for event in all_events:
        if event.event_type in ["WorkspaceCreated", "WorkspaceArchived"]:
            rebuilt_workspace_registry.apply_event(event)
        elif event.event_type in [
            "DecisionRightDelegated",
            "DelegationRevoked",
            "DelegationExpired",
        ]:
            rebuilt_delegation_graph.apply_event(event)
        elif event.event_type.startswith("Law"):
            rebuilt_law_registry.apply_event(event)

    # Verify rebuilt state matches original
    assert rebuilt_workspace_registry.to_dict() == workspace_registry.to_dict()
    assert len(rebuilt_delegation_graph.edges) == len(delegation_graph.edges)
    assert rebuilt_law_registry.get(law_id) == law_registry.get(law_id)
