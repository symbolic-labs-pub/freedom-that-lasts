"""
Tests for Law Module Handlers - Command→Event Transformation

These tests verify that commands are correctly validated and
converted to events, with all invariants enforced.
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.kernel.errors import (
    DelegationCycleDetected,
    DelegationNotFound,
    LawNotFound,
    TTLExceedsMaximum,
)
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    AdjustLaw,
    ArchiveLaw,
    CompleteLawReview,
    CreateLaw,
    CreateWorkspace,
    DelegateDecisionRight,
    RevokeDelegation,
    ScheduleLawSunset,
    TriggerLawReview,
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


# =============================================================================
# Additional Handler Tests for Complete Coverage
# =============================================================================


def test_revoke_delegation(handlers: LawCommandHandlers) -> None:
    """Test delegation revocation"""
    delegation_registry = {
        "del-1": {
            "delegation_id": "del-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "is_active": True,
            "version": 1,
        }
    }

    command = RevokeDelegation(delegation_id="del-1", reason="No longer needed")

    events = handlers.handle_revoke_delegation(
        command, command_id=generate_id(), actor_id="alice", delegation_registry=delegation_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "DelegationRevoked"
    assert event.payload["delegation_id"] == "del-1"
    assert event.payload["reason"] == "No longer needed"


def test_revoke_delegation_not_found(handlers: LawCommandHandlers) -> None:
    """Test revoke delegation fails when delegation doesn't exist"""
    delegation_registry = {}

    command = RevokeDelegation(delegation_id="nonexistent", reason="Test")

    with pytest.raises(DelegationNotFound) as exc_info:
        handlers.handle_revoke_delegation(
            command, command_id=generate_id(), actor_id="alice", delegation_registry=delegation_registry
        )

    assert exc_info.value.delegation_id == "nonexistent"


def test_trigger_law_review(handlers: LawCommandHandlers) -> None:
    """Test triggering law review"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "ACTIVE",
            "next_checkpoint_index": 2,
            "version": 3,
        }
    }

    command = TriggerLawReview(law_id="law-1", reason="Checkpoint reached")

    events = handlers.handle_trigger_law_review(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawReviewTriggered"
    assert event.payload["law_id"] == "law-1"
    assert event.payload["reason"] == "Checkpoint reached"
    assert event.payload["checkpoint_index"] == 2


def test_trigger_law_review_not_found(handlers: LawCommandHandlers) -> None:
    """Test trigger review fails when law doesn't exist"""
    law_registry = {}

    command = TriggerLawReview(law_id="nonexistent", reason="Test")

    with pytest.raises(LawNotFound) as exc_info:
        handlers.handle_trigger_law_review(
            command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
        )

    assert exc_info.value.law_id == "nonexistent"


def test_complete_law_review_continue_outcome(
    handlers: LawCommandHandlers, test_time: TestTimeProvider
) -> None:
    """Test complete review with continue outcome computes next checkpoint"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "REVIEW",
            "checkpoints": [30, 90, 180, 365],
            "activated_at": test_time.now().isoformat(),
            "next_checkpoint_index": 0,
            "version": 2,
        }
    }

    command = CompleteLawReview(law_id="law-1", outcome="continue", notes="All good")

    events = handlers.handle_complete_law_review(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawReviewCompleted"
    assert event.payload["outcome"] == "continue"
    assert event.payload["notes"] == "All good"
    assert event.payload["next_checkpoint_at"] is not None  # Next checkpoint scheduled


def test_complete_law_review_adjust_outcome(handlers: LawCommandHandlers) -> None:
    """Test complete review with adjust outcome"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "REVIEW",
            "checkpoints": [30],
            "version": 2,
        }
    }

    command = CompleteLawReview(law_id="law-1", outcome="adjust", notes="Needs adjustment")

    events = handlers.handle_complete_law_review(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawReviewCompleted"
    assert event.payload["outcome"] == "adjust"


def test_complete_law_review_sunset_outcome(handlers: LawCommandHandlers) -> None:
    """Test complete review with sunset outcome"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "REVIEW",
            "checkpoints": [30],
            "version": 2,
        }
    }

    command = CompleteLawReview(law_id="law-1", outcome="sunset", notes="Law no longer needed")

    events = handlers.handle_complete_law_review(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawReviewCompleted"
    assert event.payload["outcome"] == "sunset"


def test_complete_law_review_not_found(handlers: LawCommandHandlers) -> None:
    """Test complete review fails when law doesn't exist"""
    law_registry = {}

    command = CompleteLawReview(law_id="nonexistent", outcome="continue", notes="Test")

    with pytest.raises(LawNotFound) as exc_info:
        handlers.handle_complete_law_review(
            command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
        )

    assert exc_info.value.law_id == "nonexistent"


def test_adjust_law_with_reactivation(handlers: LawCommandHandlers, test_time: TestTimeProvider) -> None:
    """Test law adjustment emits two events: adjust + reactivate"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "ADJUST",
            "checkpoints": [30, 90, 180],
            "activated_at": test_time.now().isoformat(),
            "next_checkpoint_index": 1,
            "version": 3,
        }
    }

    command = AdjustLaw(law_id="law-1", changes={"threshold": 2000}, reason="Adjusted based on feedback")

    events = handlers.handle_adjust_law(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 2

    # First event: LawAdjusted
    adjust_event = events[0]
    assert adjust_event.event_type == "LawAdjusted"
    assert adjust_event.payload["law_id"] == "law-1"
    assert adjust_event.payload["changes"] == {"threshold": 2000}
    assert adjust_event.payload["reason"] == "Adjusted based on feedback"

    # Second event: LawActivated (reactivation)
    reactivate_event = events[1]
    assert reactivate_event.event_type == "LawActivated"
    assert reactivate_event.payload["law_id"] == "law-1"
    assert reactivate_event.payload["next_checkpoint_at"] is not None


def test_adjust_law_without_reactivation(handlers: LawCommandHandlers) -> None:
    """Test law adjustment without activated_at emits only adjust event"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "ADJUST",
            "checkpoints": [30, 90],
            # No activated_at field
            "version": 2,
        }
    }

    command = AdjustLaw(law_id="law-1", changes={"threshold": 2000}, reason="Early adjustment")

    events = handlers.handle_adjust_law(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawAdjusted"


def test_adjust_law_not_found(handlers: LawCommandHandlers) -> None:
    """Test adjust law fails when law doesn't exist"""
    law_registry = {}

    command = AdjustLaw(law_id="nonexistent", changes={"test": "value"}, reason="Test")

    with pytest.raises(LawNotFound) as exc_info:
        handlers.handle_adjust_law(
            command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
        )

    assert exc_info.value.law_id == "nonexistent"


def test_schedule_law_sunset(handlers: LawCommandHandlers, test_time: TestTimeProvider) -> None:
    """Test scheduling law for sunset"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "ACTIVE",
            "version": 4,
        }
    }

    command = ScheduleLawSunset(law_id="law-1", sunset_days=90, reason="End of pilot program")

    events = handlers.handle_schedule_law_sunset(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawSunsetScheduled"
    assert event.payload["law_id"] == "law-1"
    assert event.payload["reason"] == "End of pilot program"

    # Verify sunset date is 90 days from now
    expected_sunset = test_time.now() + timedelta(days=90)
    actual_sunset = event.payload["sunset_at"]
    if isinstance(actual_sunset, str):
        actual_sunset = datetime.fromisoformat(actual_sunset)
    assert actual_sunset == expected_sunset


def test_schedule_law_sunset_not_found(handlers: LawCommandHandlers) -> None:
    """Test schedule sunset fails when law doesn't exist"""
    law_registry = {}

    command = ScheduleLawSunset(law_id="nonexistent", sunset_days=90, reason="Test")

    with pytest.raises(LawNotFound) as exc_info:
        handlers.handle_schedule_law_sunset(
            command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
        )

    assert exc_info.value.law_id == "nonexistent"


def test_archive_law(handlers: LawCommandHandlers) -> None:
    """Test archiving a law"""
    law_registry = {
        "law-1": {
            "law_id": "law-1",
            "status": "SUNSET",
            "version": 5,
        }
    }

    command = ArchiveLaw(law_id="law-1", reason="Pilot program ended")

    events = handlers.handle_archive_law(
        command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "LawArchived"
    assert event.payload["law_id"] == "law-1"
    assert event.payload["reason"] == "Pilot program ended"


def test_archive_law_not_found(handlers: LawCommandHandlers) -> None:
    """Test archive law fails when law doesn't exist"""
    law_registry = {}

    command = ArchiveLaw(law_id="nonexistent", reason="Test")

    with pytest.raises(LawNotFound) as exc_info:
        handlers.handle_archive_law(
            command, command_id=generate_id(), actor_id="admin-1", law_registry=law_registry
        )

    assert exc_info.value.law_id == "nonexistent"
