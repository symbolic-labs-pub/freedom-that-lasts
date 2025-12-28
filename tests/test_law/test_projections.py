"""
Tests for law module projections

Tests event-sourced read models for constitutional governance.
Projections rebuild state from events - no direct state mutation.

Fun fact: Projections are like "views" in traditional databases, but better -
they're rebuil from immutable events, making time travel debugging possible!
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.law.models import LawStatus
from freedom_that_lasts.law.projections import (
    WorkspaceRegistry,
    DelegationGraph,
    LawRegistry,
)


def create_event(
    event_id: str,
    stream_id: str,
    stream_type: str,
    event_type: str,
    occurred_at: datetime,
    command_id: str,
    actor_id: str,
    payload: dict,
    version: int,
) -> Event:
    """Helper to create events for testing"""
    return Event(
        event_id=event_id,
        stream_id=stream_id,
        stream_type=stream_type,
        event_type=event_type,
        occurred_at=occurred_at,
        command_id=command_id,
        actor_id=actor_id,
        payload=payload,
        version=version,
    )


# =============================================================================
# WorkspaceRegistry Tests
# =============================================================================


def test_workspace_registry_initial_state():
    """Test registry starts empty"""
    registry = WorkspaceRegistry()
    assert registry.workspaces == {}
    assert registry.list_active() == []


def test_workspace_created_adds_workspace(test_time):
    """Test WorkspaceCreated event adds workspace"""
    registry = WorkspaceRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="ws-1",
        stream_type="Workspace",
        event_type="WorkspaceCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "ws-1",
            "name": "Test Workspace",
            "parent_workspace_id": None,
            "scope": {"domain": "procurement"},
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )

    registry.apply_event(event)

    workspace = registry.get("ws-1")
    assert workspace is not None
    assert workspace["workspace_id"] == "ws-1"
    assert workspace["name"] == "Test Workspace"
    assert workspace["parent_workspace_id"] is None
    assert workspace["scope"] == {"domain": "procurement"}
    assert workspace["is_active"] is True
    assert workspace["version"] == 1


def test_workspace_archived_marks_inactive(test_time):
    """Test WorkspaceArchived event marks workspace as inactive"""
    registry = WorkspaceRegistry()

    # First create workspace
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="ws-1",
        stream_type="Workspace",
        event_type="WorkspaceCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "ws-1",
            "name": "Test Workspace",
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Then archive it
    archive_event = create_event(
        event_id=generate_id(),
        stream_id="ws-1",
        stream_type="Workspace",
        event_type="WorkspaceArchived",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "ws-1",
            "archived_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(archive_event)

    workspace = registry.get("ws-1")
    assert workspace is not None
    assert workspace["is_active"] is False
    assert "archived_at" in workspace


def test_workspace_archived_nonexistent_workspace(test_time):
    """Test WorkspaceArchived event for non-existent workspace is ignored"""
    registry = WorkspaceRegistry()

    archive_event = create_event(
        event_id=generate_id(),
        stream_id="nonexistent",
        stream_type="Workspace",
        event_type="WorkspaceArchived",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "nonexistent",
            "archived_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(archive_event)

    # Should not crash, just ignore
    assert registry.get("nonexistent") is None


def test_workspace_get_nonexistent_returns_none():
    """Test get() returns None for non-existent workspace"""
    registry = WorkspaceRegistry()
    assert registry.get("nonexistent") is None


def test_workspace_list_active_filters_archived(test_time):
    """Test list_active() excludes archived workspaces"""
    registry = WorkspaceRegistry()

    # Create two workspaces
    for i in range(1, 3):
        event = create_event(
            event_id=generate_id(),
            stream_id=f"ws-{i}",
            stream_type="Workspace",
            event_type="WorkspaceCreated",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload={
                "workspace_id": f"ws-{i}",
                "name": f"Workspace {i}",
                "created_at": test_time.now().isoformat(),
            },
            version=1,
        )
        registry.apply_event(event)

    # Archive one
    archive_event = create_event(
        event_id=generate_id(),
        stream_id="ws-1",
        stream_type="Workspace",
        event_type="WorkspaceArchived",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "ws-1",
            "archived_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(archive_event)

    active = registry.list_active()
    assert len(active) == 1
    assert active[0]["workspace_id"] == "ws-2"


def test_workspace_serialization_round_trip(test_time):
    """Test to_dict() and from_dict() preserve state"""
    registry = WorkspaceRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="ws-1",
        stream_type="Workspace",
        event_type="WorkspaceCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "workspace_id": "ws-1",
            "name": "Test Workspace",
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(event)

    # Serialize and deserialize
    data = registry.to_dict()
    restored = WorkspaceRegistry.from_dict(data)

    assert restored.get("ws-1") == registry.get("ws-1")


# =============================================================================
# DelegationGraph Tests
# =============================================================================


def test_delegation_graph_initial_state():
    """Test graph starts empty"""
    graph = DelegationGraph()
    assert graph.delegations == {}
    assert graph.edges == []


def test_decision_right_delegated_creates_delegation(test_time):
    """Test DecisionRightDelegated event creates delegation and edge"""
    graph = DelegationGraph()

    expires_at = test_time.now() + timedelta(days=90)
    event = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": test_time.now().isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
            "renewable": True,
            "visibility": "public",
            "purpose_tag": "procurement",
        },
        version=1,
    )

    graph.apply_event(event)

    delegation = graph.get("del-1")
    assert delegation is not None
    assert delegation["delegation_id"] == "del-1"
    assert delegation["from_actor"] == "alice"
    assert delegation["to_actor"] == "bob"
    assert delegation["is_active"] is True
    assert delegation["revoked_at"] is None

    # Check edge was created
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.delegation_id == "del-1"
    assert edge.from_actor == "alice"
    assert edge.to_actor == "bob"
    assert edge.is_active is True


def test_delegation_revoked_marks_inactive(test_time):
    """Test DelegationRevoked event marks delegation and edge as inactive"""
    graph = DelegationGraph()

    # First create delegation
    expires_at = test_time.now() + timedelta(days=90)
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": test_time.now().isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(create_event_obj)

    # Then revoke it
    revoke_event = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DelegationRevoked",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "revoked_at": test_time.now().isoformat(),
        },
        version=2,
    )
    graph.apply_event(revoke_event)

    delegation = graph.get("del-1")
    assert delegation is not None
    assert delegation["is_active"] is False
    assert delegation["revoked_at"] is not None

    # Check edge was marked inactive
    edge = graph.edges[0]
    assert edge.is_active is False


def test_delegation_revoked_nonexistent_delegation(test_time):
    """Test DelegationRevoked for non-existent delegation is ignored"""
    graph = DelegationGraph()

    revoke_event = create_event(
        event_id=generate_id(),
        stream_id="nonexistent",
        stream_type="Delegation",
        event_type="DelegationRevoked",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "nonexistent",
            "revoked_at": test_time.now().isoformat(),
        },
        version=1,
    )
    graph.apply_event(revoke_event)

    # Should not crash, just ignore
    assert graph.get("nonexistent") is None


def test_delegation_expired_marks_inactive(test_time):
    """Test DelegationExpired event marks delegation and edge as inactive"""
    graph = DelegationGraph()

    # First create delegation
    expires_at = test_time.now() + timedelta(days=90)
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": test_time.now().isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(create_event_obj)

    # Then expire it
    expire_event = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DelegationExpired",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "delegation_id": "del-1",
        },
        version=2,
    )
    graph.apply_event(expire_event)

    delegation = graph.get("del-1")
    assert delegation is not None
    assert delegation["is_active"] is False

    # Check edge was marked inactive
    edge = graph.edges[0]
    assert edge.is_active is False


def test_delegation_expired_nonexistent_delegation(test_time):
    """Test DelegationExpired for non-existent delegation is ignored"""
    graph = DelegationGraph()

    expire_event = create_event(
        event_id=generate_id(),
        stream_id="nonexistent",
        stream_type="Delegation",
        event_type="DelegationExpired",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "delegation_id": "nonexistent",
        },
        version=1,
    )
    graph.apply_event(expire_event)

    # Should not crash, just ignore
    assert graph.get("nonexistent") is None


def test_get_active_edges_filters_by_expiry(test_time):
    """Test get_active_edges() filters expired and inactive delegations"""
    graph = DelegationGraph()

    now = test_time.now()
    future = now + timedelta(days=90)
    past = now - timedelta(days=10)

    # Create active delegation (expires in future)
    active_event = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": future.isoformat(),
        },
        version=1,
    )
    graph.apply_event(active_event)

    # Create expired delegation (expires in past)
    expired_event = create_event(
        event_id=generate_id(),
        stream_id="del-2",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="charlie",
        payload={
            "delegation_id": "del-2",
            "workspace_id": "ws-1",
            "from_actor": "charlie",
            "to_actor": "david",
            "delegated_at": now.isoformat(),
            "ttl_days": 1,
            "expires_at": past.isoformat(),
        },
        version=1,
    )
    graph.apply_event(expired_event)

    active_edges = graph.get_active_edges(now)
    assert len(active_edges) == 1
    assert active_edges[0].delegation_id == "del-1"


def test_get_delegations_by_actor(test_time):
    """Test get_delegations_by_actor() returns delegations from specific actor"""
    graph = DelegationGraph()

    now = test_time.now()
    expires_at = now + timedelta(days=90)

    # Alice delegates to Bob
    event1 = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(event1)

    # Charlie delegates to David
    event2 = create_event(
        event_id=generate_id(),
        stream_id="del-2",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="charlie",
        payload={
            "delegation_id": "del-2",
            "workspace_id": "ws-1",
            "from_actor": "charlie",
            "to_actor": "david",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(event2)

    alice_delegations = graph.get_delegations_by_actor("alice")
    assert len(alice_delegations) == 1
    assert alice_delegations[0]["delegation_id"] == "del-1"

    charlie_delegations = graph.get_delegations_by_actor("charlie")
    assert len(charlie_delegations) == 1
    assert charlie_delegations[0]["delegation_id"] == "del-2"


def test_get_delegations_to_actor(test_time):
    """Test get_delegations_to_actor() returns delegations to specific actor"""
    graph = DelegationGraph()

    now = test_time.now()
    expires_at = now + timedelta(days=90)

    # Alice delegates to Bob
    event1 = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(event1)

    # Charlie delegates to Bob
    event2 = create_event(
        event_id=generate_id(),
        stream_id="del-2",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="charlie",
        payload={
            "delegation_id": "del-2",
            "workspace_id": "ws-1",
            "from_actor": "charlie",
            "to_actor": "bob",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(event2)

    bob_delegations = graph.get_delegations_to_actor("bob")
    assert len(bob_delegations) == 2
    delegation_ids = {d["delegation_id"] for d in bob_delegations}
    assert delegation_ids == {"del-1", "del-2"}


def test_delegation_graph_serialization_round_trip(test_time):
    """Test to_dict() and from_dict() preserve state including edges"""
    graph = DelegationGraph()

    now = test_time.now()
    expires_at = now + timedelta(days=90)

    event = create_event(
        event_id=generate_id(),
        stream_id="del-1",
        stream_type="Delegation",
        event_type="DecisionRightDelegated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="alice",
        payload={
            "delegation_id": "del-1",
            "workspace_id": "ws-1",
            "from_actor": "alice",
            "to_actor": "bob",
            "delegated_at": now.isoformat(),
            "ttl_days": 90,
            "expires_at": expires_at.isoformat(),
        },
        version=1,
    )
    graph.apply_event(event)

    # Serialize and deserialize
    data = graph.to_dict()
    restored = DelegationGraph.from_dict(data)

    assert restored.get("del-1") == graph.get("del-1")
    assert len(restored.edges) == len(graph.edges)
    assert restored.edges[0].delegation_id == graph.edges[0].delegation_id


# =============================================================================
# LawRegistry Tests
# =============================================================================


def test_law_registry_initial_state():
    """Test registry starts empty"""
    registry = LawRegistry()
    assert registry.laws == {}
    assert registry.list_active() == []


def test_law_created_adds_law(test_time):
    """Test LawCreated event adds law in DRAFT status"""
    registry = LawRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Procurement Law",
            "scope": {"domain": "procurement"},
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30, 90, 180],
            "params": {"threshold": 1000},
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )

    registry.apply_event(event)

    law = registry.get("law-1")
    assert law is not None
    assert law["law_id"] == "law-1"
    assert law["title"] == "Procurement Law"
    assert law["status"] == "DRAFT"
    assert law["activated_at"] is None
    assert law["next_checkpoint_at"] is None
    assert law["version"] == 1


def test_law_activated_changes_status(test_time):
    """Test LawActivated event changes status to ACTIVE"""
    registry = LawRegistry()

    # First create law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Then activate it
    next_checkpoint = test_time.now() + timedelta(days=30)
    activate_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawActivated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "activated_at": test_time.now().isoformat(),
            "next_checkpoint_at": next_checkpoint.isoformat(),
            "next_checkpoint_index": 0,
        },
        version=2,
    )
    registry.apply_event(activate_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "ACTIVE"
    assert law["activated_at"] is not None
    assert law["next_checkpoint_at"] is not None
    assert law["next_checkpoint_index"] == 0


def test_law_review_triggered_changes_status(test_time):
    """Test LawReviewTriggered event changes status to REVIEW"""
    registry = LawRegistry()

    # Create and activate law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Trigger review
    review_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawReviewTriggered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "law_id": "law-1",
            "triggered_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(review_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "REVIEW"
    assert "review_triggered_at" in law


def test_law_review_completed_continue_outcome(test_time):
    """Test LawReviewCompleted with continue outcome returns to ACTIVE"""
    registry = LawRegistry()

    # Create law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Complete review with "continue" outcome
    next_checkpoint = test_time.now() + timedelta(days=30)
    review_complete_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawReviewCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "outcome": "continue",
            "next_checkpoint_at": next_checkpoint.isoformat(),
        },
        version=2,
    )
    registry.apply_event(review_complete_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "ACTIVE"
    assert law["next_checkpoint_at"] is not None


def test_law_review_completed_adjust_outcome(test_time):
    """Test LawReviewCompleted with adjust outcome changes to ADJUST"""
    registry = LawRegistry()

    # Create law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Complete review with "adjust" outcome
    review_complete_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawReviewCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "outcome": "adjust",
        },
        version=2,
    )
    registry.apply_event(review_complete_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "ADJUST"


def test_law_review_completed_sunset_outcome(test_time):
    """Test LawReviewCompleted with sunset outcome changes to SUNSET"""
    registry = LawRegistry()

    # Create law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Complete review with "sunset" outcome
    review_complete_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawReviewCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "outcome": "sunset",
        },
        version=2,
    )
    registry.apply_event(review_complete_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "SUNSET"


def test_law_archived_changes_status(test_time):
    """Test LawArchived event changes status to ARCHIVED"""
    registry = LawRegistry()

    # Create law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    # Archive it
    archive_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawArchived",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "archived_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(archive_event)

    law = registry.get("law-1")
    assert law is not None
    assert law["status"] == "ARCHIVED"
    assert "archived_at" in law


def test_law_get_nonexistent_returns_none():
    """Test get() returns None for non-existent law"""
    registry = LawRegistry()
    assert registry.get("nonexistent") is None


def test_law_list_by_status(test_time):
    """Test list_by_status() filters by status correctly"""
    registry = LawRegistry()

    # Create two laws
    for i in range(1, 3):
        event = create_event(
            event_id=generate_id(),
            stream_id=f"law-{i}",
            stream_type="Law",
            event_type="LawCreated",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload={
                "law_id": f"law-{i}",
                "workspace_id": "ws-1",
                "title": f"Law {i}",
                "reversibility_class": "REVERSIBLE",
                "checkpoints": [30],
                "created_at": test_time.now().isoformat(),
            },
            version=1,
        )
        registry.apply_event(event)

    # Activate one
    activate_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawActivated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "activated_at": test_time.now().isoformat(),
            "next_checkpoint_at": (test_time.now() + timedelta(days=30)).isoformat(),
            "next_checkpoint_index": 0,
        },
        version=2,
    )
    registry.apply_event(activate_event)

    draft_laws = registry.list_by_status(LawStatus.DRAFT)
    assert len(draft_laws) == 1
    assert draft_laws[0]["law_id"] == "law-2"

    active_laws = registry.list_by_status(LawStatus.ACTIVE)
    assert len(active_laws) == 1
    assert active_laws[0]["law_id"] == "law-1"


def test_law_list_active(test_time):
    """Test list_active() returns only ACTIVE laws"""
    registry = LawRegistry()

    # Create and activate law
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    activate_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawActivated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "activated_at": test_time.now().isoformat(),
            "next_checkpoint_at": (test_time.now() + timedelta(days=30)).isoformat(),
            "next_checkpoint_index": 0,
        },
        version=2,
    )
    registry.apply_event(activate_event)

    active_laws = registry.list_active()
    assert len(active_laws) == 1
    assert active_laws[0]["law_id"] == "law-1"


def test_law_list_overdue_reviews(test_time):
    """Test list_overdue_reviews() returns laws with past checkpoints"""
    registry = LawRegistry()

    now = test_time.now()
    past_checkpoint = now - timedelta(days=10)

    # Create and activate law with past checkpoint
    create_event_obj = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": now.isoformat(),
        },
        version=1,
    )
    registry.apply_event(create_event_obj)

    activate_event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawActivated",
        occurred_at=now,
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "activated_at": now.isoformat(),
            "next_checkpoint_at": past_checkpoint.isoformat(),
            "next_checkpoint_index": 0,
        },
        version=2,
    )
    registry.apply_event(activate_event)

    overdue = registry.list_overdue_reviews(now)
    assert len(overdue) == 1
    assert overdue[0]["law_id"] == "law-1"


def test_law_registry_serialization_round_trip(test_time):
    """Test to_dict() and from_dict() preserve state"""
    registry = LawRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "law_id": "law-1",
            "workspace_id": "ws-1",
            "title": "Test Law",
            "reversibility_class": "REVERSIBLE",
            "checkpoints": [30],
            "created_at": test_time.now().isoformat(),
        },
        version=1,
    )
    registry.apply_event(event)

    # Serialize and deserialize
    data = registry.to_dict()
    restored = LawRegistry.from_dict(data)

    assert restored.get("law-1") == registry.get("law-1")
