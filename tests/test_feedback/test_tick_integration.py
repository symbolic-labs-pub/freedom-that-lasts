"""
Integration Tests for TickEngine - Complete trigger evaluation loop

These tests verify that the complete tick workflow functions correctly:
load state → evaluate triggers → emit events → compute health
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.feedback.models import RiskLevel
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
from freedom_that_lasts.law.models import ReversibilityClass
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry, WorkspaceRegistry


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide deterministic time"""
    return TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def event_store(tmp_path) -> SQLiteEventStore:
    """Provide event store"""
    db_path = tmp_path / "test_tick.db"
    return SQLiteEventStore(str(db_path))


@pytest.fixture
def safety_policy() -> SafetyPolicy:
    """Provide safety policy"""
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


def test_tick_healthy_system(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """Test tick on healthy system - GREEN status"""
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    # Create minimal system state
    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Create workspace
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create a few delegations (low concentration)
    for i, to_actor in enumerate(["bob", "charlie", "dave"]):
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
            [],
        )
        for event in del_events:
            delegation_graph.apply_event(event)

    # Create and activate law (not overdue)
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

    law_id = law_events[0].payload["law_id"]
    activate = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in activate_events:
        law_registry.apply_event(event)

    # Run tick
    result = tick_engine.tick(delegation_graph, law_registry)

    # Verify healthy system
    assert result.freedom_health.risk_level == RiskLevel.GREEN
    assert not result.has_warnings()
    assert not result.has_halts()
    assert len(result.triggered_events) == 0


def test_tick_concentration_warning(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """Test tick with concentration warning"""
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Create workspace
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create concentrated delegations (unequal distribution)
    # Bob gets many, others get few - this creates inequality
    # Bob: 35, charlie: 3, dave: 2 - Gini ~0.54 > 0.5 warning threshold
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

    # Add a few to charlie and dave for inequality
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
    result = tick_engine.tick(delegation_graph, law_registry)

    # Verify warning triggered
    assert result.freedom_health.risk_level == RiskLevel.YELLOW
    assert result.has_warnings()
    assert not result.has_halts()

    # Should have concentration warning event
    warning_events = [
        e for e in result.triggered_events if e.event_type == "DelegationConcentrationWarning"
    ]
    assert len(warning_events) == 1


def test_tick_concentration_halt(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """Test tick with concentration halt"""
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Create workspace
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create extreme concentration (triggers halt)
    for i in range(150):  # Above halt threshold
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
    result = tick_engine.tick(delegation_graph, law_registry)

    # Verify halt triggered
    assert result.freedom_health.risk_level == RiskLevel.RED
    assert result.has_halts()

    # Should have halt + transparency escalation
    halt_events = [
        e for e in result.triggered_events if e.event_type == "DelegationConcentrationHalt"
    ]
    transparency_events = [
        e for e in result.triggered_events if e.event_type == "TransparencyEscalated"
    ]

    assert len(halt_events) == 1
    assert len(transparency_events) == 1


def test_tick_overdue_law_reviews(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
    handlers: LawCommandHandlers,
) -> None:
    """Test tick triggers overdue law reviews"""
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Create workspace
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create and activate laws
    for i in range(3):
        create_law = CreateLaw(
            workspace_id=workspace_id,
            title=f"Law {i}",
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

        law_id = law_events[0].payload["law_id"]
        activate = ActivateLaw(law_id=law_id)
        activate_events = handlers.handle_activate_law(
            activate, generate_id(), "alice", law_registry.to_dict()["laws"]
        )
        for event in activate_events:
            law_registry.apply_event(event)

    # Advance time past first checkpoint (30 days)
    test_time.advance_days(35)

    # Run tick
    result = tick_engine.tick(delegation_graph, law_registry)

    # Verify review triggers
    assert result.freedom_health.risk_level == RiskLevel.YELLOW
    review_events = [
        e for e in result.triggered_events if e.event_type == "LawReviewTriggered"
    ]
    assert len(review_events) == 3  # All 3 laws are overdue


def test_tick_summary(
    event_store: SQLiteEventStore,
    test_time: TestTimeProvider,
    safety_policy: SafetyPolicy,
) -> None:
    """Test tick result summary"""
    tick_engine = TickEngine(event_store, test_time, safety_policy)

    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    result = tick_engine.tick(delegation_graph, law_registry)

    summary = result.summary()
    assert result.tick_id in summary
    assert "GREEN" in summary  # Risk level
    assert "Events: 0" in summary  # No triggers
