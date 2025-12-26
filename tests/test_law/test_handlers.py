"""
Tests for Law Module Handlers - Command→Event Transformation

These tests verify that commands are correctly validated and
converted to events, with all invariants enforced.
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.kernel.errors import DelegationCycleDetected, TTLExceedsMaximum
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    CreateLaw,
    CreateWorkspace,
    DelegateDecisionRight,
)
from freedom_that_lasts.law.handlers import LawCommandHandlers
from freedom_that_lasts.law.models import DelegationEdge, ReversibilityClass
from freedom_that_lasts.law.projections import DelegationGraph, LawRegistry, WorkspaceRegistry


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide deterministic time for tests"""
    return TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def safety_policy() -> SafetyPolicy:
    """Provide default safety policy"""
    return SafetyPolicy()


@pytest.fixture
def handlers(test_time: TestTimeProvider, safety_policy: SafetyPolicy) -> LawCommandHandlers:
    """Provide command handlers with test dependencies"""
    return LawCommandHandlers(test_time, safety_policy)


def test_create_workspace(handlers: LawCommandHandlers) -> None:
    """Test workspace creation"""
    command = CreateWorkspace(
        name="Health Services", parent_workspace_id=None, scope={"territory": "Budapest"}
    )

    events = handlers.handle_create_workspace(
        command, command_id=generate_id(), actor_id="alice"
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "WorkspaceCreated"
    assert event.payload["name"] == "Health Services"
    assert event.payload["scope"]["territory"] == "Budapest"


def test_delegate_within_ttl_bounds(
    handlers: LawCommandHandlers, test_time: TestTimeProvider
) -> None:
    """Test delegation with TTL within policy bounds"""
    # Create workspace first
    workspace_registry = {"ws-1": {"workspace_id": "ws-1", "name": "Test"}}
    delegation_edges: list[DelegationEdge] = []

    command = DelegateDecisionRight(
        from_actor="alice",
        workspace_id="ws-1",
        to_actor="bob",
        ttl_days=180,  # Within 365 day limit
    )

    events = handlers.handle_delegate_decision_right(
        command,
        command_id=generate_id(),
        actor_id="alice",
        workspace_registry=workspace_registry,
        delegation_edges=delegation_edges,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "DecisionRightDelegated"
    assert event.payload["from_actor"] == "alice"
    assert event.payload["to_actor"] == "bob"
    assert event.payload["ttl_days"] == 180


def test_delegate_exceeds_ttl_limit(
    handlers: LawCommandHandlers, safety_policy: SafetyPolicy
) -> None:
    """Test that delegation exceeding TTL limit is rejected"""
    workspace_registry = {"ws-1": {"workspace_id": "ws-1"}}
    delegation_edges: list[DelegationEdge] = []

    command = DelegateDecisionRight(
        from_actor="alice",
        workspace_id="ws-1",
        to_actor="bob",
        ttl_days=400,  # Exceeds 365 day limit
    )

    with pytest.raises(TTLExceedsMaximum) as exc_info:
        handlers.handle_delegate_decision_right(
            command,
            command_id=generate_id(),
            actor_id="alice",
            workspace_registry=workspace_registry,
            delegation_edges=delegation_edges,
        )

    assert exc_info.value.ttl_days == 400
    assert exc_info.value.max_ttl_days == safety_policy.max_delegation_ttl_days


def test_delegate_creates_cycle(
    handlers: LawCommandHandlers, test_time: TestTimeProvider
) -> None:
    """Test that delegation creating a cycle is rejected"""
    workspace_registry = {"ws-1": {"workspace_id": "ws-1"}}

    # Existing chain: alice -> bob -> charlie
    from datetime import timedelta

    future = test_time.now() + timedelta(days=180)
    delegation_edges = [
        DelegationEdge(
            delegation_id="del-1",
            from_actor="alice",
            to_actor="bob",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-2",
            from_actor="bob",
            to_actor="charlie",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    # Try to create charlie -> alice (would create cycle)
    command = DelegateDecisionRight(
        from_actor="charlie",
        workspace_id="ws-1",
        to_actor="alice",
        ttl_days=180,
    )

    with pytest.raises(DelegationCycleDetected) as exc_info:
        handlers.handle_delegate_decision_right(
            command,
            command_id=generate_id(),
            actor_id="charlie",
            workspace_registry=workspace_registry,
            delegation_edges=delegation_edges,
        )

    assert exc_info.value.from_actor == "charlie"
    assert exc_info.value.to_actor == "alice"


def test_create_law(handlers: LawCommandHandlers) -> None:
    """Test law creation"""
    workspace_registry = {"ws-1": {"workspace_id": "ws-1", "name": "Test"}}

    command = CreateLaw(
        workspace_id="ws-1",
        title="Primary Care Pilot",
        scope={"territory": "District5"},
        reversibility_class=ReversibilityClass.SEMI_REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={"max_wait_days": 10},
    )

    events = handlers.handle_create_law(
        command,
        command_id=generate_id(),
        actor_id="alice",
        workspace_registry=workspace_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawCreated"
    assert event.payload["title"] == "Primary Care Pilot"
    assert event.payload["reversibility_class"] == "SEMI_REVERSIBLE"
    assert event.payload["checkpoints"] == [30, 90, 180, 365]


def test_activate_law(handlers: LawCommandHandlers, test_time: TestTimeProvider) -> None:
    """Test law activation sets checkpoint"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "checkpoints": [30, 90, 180, 365],
            "status": "DRAFT",
            "version": 1,
        }
    }

    command = ActivateLaw(law_id="law-1")

    events = handlers.handle_activate_law(
        command, command_id=generate_id(), actor_id="alice", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawActivated"
    assert event.payload["law_id"] == "law-1"
    assert event.payload["next_checkpoint_at"] is not None  # First checkpoint scheduled

    # Verify checkpoint is 30 days from now
    from datetime import timedelta

    expected_checkpoint = test_time.now() + timedelta(days=30)
    actual_checkpoint = event.payload["next_checkpoint_at"]

    # Handle both datetime and string
    if isinstance(actual_checkpoint, str):
        actual_checkpoint = datetime.fromisoformat(actual_checkpoint)

    assert actual_checkpoint == expected_checkpoint
