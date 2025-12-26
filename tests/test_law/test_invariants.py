"""
Tests for Law Module Invariants - The Constitutional Constraints

These tests verify that the anti-tyranny safeguards work correctly.
They test the pure invariant functions that enforce the system's
non-negotiable rules.

Fun fact: These tests are like unit tests for the "laws of physics"
of our governance universe!
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.kernel.errors import (
    DelegationCycleDetected,
    InvalidCheckpointSchedule,
    TTLExceedsMaximum,
)
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.law.invariants import (
    compute_graph_depth,
    compute_in_degrees,
    find_cycles,
    validate_acyclic_delegation,
    validate_checkpoint_schedule,
    validate_delegation_ttl,
)
from freedom_that_lasts.law.models import DelegationEdge


def test_ttl_validation_within_bounds() -> None:
    """Test that TTL within policy bounds is accepted"""
    policy = SafetyPolicy(max_delegation_ttl_days=365)

    # Should not raise
    validate_delegation_ttl(180, policy)
    validate_delegation_ttl(365, policy)
    validate_delegation_ttl(1, policy)


def test_ttl_validation_exceeds_maximum() -> None:
    """Test that TTL exceeding policy maximum is rejected"""
    policy = SafetyPolicy(max_delegation_ttl_days=365)

    with pytest.raises(TTLExceedsMaximum) as exc_info:
        validate_delegation_ttl(366, policy)

    assert exc_info.value.ttl_days == 366
    assert exc_info.value.max_ttl_days == 365


def test_acyclic_delegation_no_cycle() -> None:
    """Test that acyclic delegations are accepted"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create a simple chain: A -> B -> C
    edges = [
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

    # Adding D -> E should be fine (no cycle)
    validate_acyclic_delegation(edges, "david", "eve", now)

    # Adding A -> D should be fine (no cycle)
    validate_acyclic_delegation(edges, "alice", "david", now)


def test_acyclic_delegation_detects_simple_cycle() -> None:
    """Test that simple cycles are detected"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create chain: A -> B -> C
    edges = [
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

    # Adding C -> A would create cycle: A -> B -> C -> A
    with pytest.raises(DelegationCycleDetected) as exc_info:
        validate_acyclic_delegation(edges, "charlie", "alice", now)

    assert exc_info.value.from_actor == "charlie"
    assert exc_info.value.to_actor == "alice"


def test_acyclic_delegation_detects_complex_cycle() -> None:
    """Test that longer cycles are detected"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create chain: A -> B -> C -> D -> E
    edges = [
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
        DelegationEdge(
            delegation_id="del-3",
            from_actor="charlie",
            to_actor="david",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-4",
            from_actor="david",
            to_actor="eve",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    # Adding E -> B would create cycle involving B, C, D, E
    with pytest.raises(DelegationCycleDetected):
        validate_acyclic_delegation(edges, "eve", "bob", now)


def test_acyclic_delegation_ignores_expired() -> None:
    """Test that expired delegations are ignored for cycle detection"""
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=180)

    # Create expired chain: A -> B (expired)
    edges = [
        DelegationEdge(
            delegation_id="del-1",
            from_actor="alice",
            to_actor="bob",
            workspace_id="ws-1",
            expires_at=past,  # Expired!
            is_active=True,
        ),
    ]

    # Adding B -> A should be fine because A -> B is expired
    validate_acyclic_delegation(edges, "bob", "alice", now)


def test_checkpoint_schedule_valid() -> None:
    """Test that valid checkpoint schedules are accepted"""
    policy = SafetyPolicy(law_min_checkpoint_schedule=[30, 90, 180, 365])

    # Exact match
    validate_checkpoint_schedule([30, 90, 180, 365], policy)

    # More frequent is fine
    validate_checkpoint_schedule([30, 60, 90, 120, 180, 365], policy)

    # Close enough (within tolerance)
    validate_checkpoint_schedule([28, 88, 178, 362], policy)


def test_checkpoint_schedule_missing_required() -> None:
    """Test that missing required checkpoints is rejected"""
    policy = SafetyPolicy(law_min_checkpoint_schedule=[30, 90, 180, 365])

    # Missing 30-day checkpoint
    with pytest.raises(InvalidCheckpointSchedule):
        validate_checkpoint_schedule([90, 180, 365], policy)

    # Missing 365-day checkpoint
    with pytest.raises(InvalidCheckpointSchedule):
        validate_checkpoint_schedule([30, 90, 180], policy)


def test_checkpoint_schedule_empty() -> None:
    """Test that empty checkpoint schedule is rejected"""
    policy = SafetyPolicy()

    with pytest.raises(InvalidCheckpointSchedule):
        validate_checkpoint_schedule([], policy)


def test_compute_in_degrees() -> None:
    """Test in-degree computation for concentration analysis"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create network where Bob receives 3 delegations
    edges = [
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
            from_actor="charlie",
            to_actor="bob",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-3",
            from_actor="david",
            to_actor="bob",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-4",
            from_actor="bob",
            to_actor="eve",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    in_degrees = compute_in_degrees(edges, now)

    assert in_degrees["bob"] == 3  # Bob receives 3 delegations
    assert in_degrees["eve"] == 1  # Eve receives 1 delegation
    assert "alice" not in in_degrees  # Alice receives 0


def test_find_cycles_empty_graph() -> None:
    """Test that empty graph has no cycles"""
    now = datetime.now(timezone.utc)
    cycles = find_cycles([], now)
    assert cycles == []


def test_find_cycles_detects_cycle() -> None:
    """Test that cycles are found in graph"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create a cycle: A -> B -> C -> A
    edges = [
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
        DelegationEdge(
            delegation_id="del-3",
            from_actor="charlie",
            to_actor="alice",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    cycles = find_cycles(edges, now)

    # Should find at least one cycle
    assert len(cycles) > 0

    # Cycle should involve alice, bob, charlie
    cycle = cycles[0]
    assert "alice" in cycle
    assert "bob" in cycle
    assert "charlie" in cycle


def test_compute_graph_depth_simple_chain() -> None:
    """Test graph depth computation for simple delegation chain"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Create chain: Alice -> Bob -> Charlie -> David
    edges = [
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
        DelegationEdge(
            delegation_id="del-3",
            from_actor="charlie",
            to_actor="david",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    depths = compute_graph_depth(edges, now)

    assert depths["alice"] == 0  # Root (no incoming)
    assert depths["bob"] == 1  # 1 hop from root
    assert depths["charlie"] == 2  # 2 hops from root
    assert depths["david"] == 3  # 3 hops from root


def test_compute_graph_depth_multiple_roots() -> None:
    """Test graph depth with multiple independent roots"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Two separate chains:
    # Alice -> Bob
    # Carol -> David
    edges = [
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
            from_actor="carol",
            to_actor="david",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    depths = compute_graph_depth(edges, now)

    assert depths["alice"] == 0  # Root 1
    assert depths["bob"] == 1
    assert depths["carol"] == 0  # Root 2
    assert depths["david"] == 1


def test_compute_graph_depth_converging_chains() -> None:
    """Test graph depth when multiple chains converge"""
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=180)

    # Multiple actors delegate to Eve:
    # Alice -> Bob -> Eve
    # Carol -> David -> Eve
    edges = [
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
            to_actor="eve",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-3",
            from_actor="carol",
            to_actor="david",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
        DelegationEdge(
            delegation_id="del-4",
            from_actor="david",
            to_actor="eve",
            workspace_id="ws-1",
            expires_at=future,
            is_active=True,
        ),
    ]

    depths = compute_graph_depth(edges, now)

    # Eve should have maximum depth from either chain
    assert depths["eve"] == 2  # Max of (Alice->Bob->Eve=2, Carol->David->Eve=2)


def test_compute_graph_depth_empty_graph() -> None:
    """Test graph depth on empty graph"""
    now = datetime.now(timezone.utc)
    depths = compute_graph_depth([], now)
    assert depths == {}


def test_compute_graph_depth_ignores_expired() -> None:
    """Test that expired delegations are ignored in depth computation"""
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=180)

    # Alice -> Bob (active), Bob -> Charlie (expired)
    edges = [
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
            expires_at=past,  # Expired!
            is_active=True,
        ),
    ]

    depths = compute_graph_depth(edges, now)

    assert depths["alice"] == 0
    assert depths["bob"] == 1
    assert "charlie" not in depths  # Excluded (expired edge)
