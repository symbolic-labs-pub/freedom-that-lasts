"""
Tests for FTL Façade - Public API

These tests verify that the FTL façade provides a clean,
high-level API that works correctly.
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.feedback.models import RiskLevel
from freedom_that_lasts.ftl import FTL
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.models import ReversibilityClass


def test_ftl_init_creates_database(tmp_path):
    """Test FTL initialization creates database"""
    db_path = tmp_path / "test.db"

    ftl = FTL(str(db_path))

    assert db_path.exists()
    assert ftl.event_store is not None
    assert ftl.workspace_registry is not None


def test_ftl_rebuild_projections_from_events(tmp_path):
    """Test FTL rebuilds projections from event store"""
    db_path = tmp_path / "test.db"

    # Create some data
    ftl1 = FTL(str(db_path))
    workspace = ftl1.create_workspace("Test")
    workspace_id = workspace["workspace_id"]

    # Create new instance - should rebuild projections
    ftl2 = FTL(str(db_path))

    workspaces = ftl2.list_workspaces()
    assert len(workspaces) == 1
    assert workspaces[0]["workspace_id"] == workspace_id


def test_ftl_create_workspace(tmp_path):
    """Test workspace creation through façade"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace(
        name="Health Services", scope={"territory": "Budapest"}
    )

    assert workspace["name"] == "Health Services"
    assert workspace["scope"]["territory"] == "Budapest"
    assert "workspace_id" in workspace


def test_ftl_list_workspaces(tmp_path):
    """Test listing workspaces"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    ftl.create_workspace("WS1")
    ftl.create_workspace("WS2")

    workspaces = ftl.list_workspaces()
    assert len(workspaces) == 2


def test_ftl_delegate(tmp_path):
    """Test delegation through façade"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    delegation = ftl.delegate(
        from_actor="alice",
        workspace_id=workspace["workspace_id"],
        to_actor="bob",
        ttl_days=180,
    )

    assert delegation["from_actor"] == "alice"
    assert delegation["to_actor"] == "bob"
    assert delegation["ttl_days"] == 180


def test_ftl_create_and_activate_law(tmp_path):
    """Test law creation and activation"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test Law",
        scope={"territory": "Test"},
        reversibility_class="REVERSIBLE",
        checkpoints=[30, 90, 180, 365],
        params={"test": "value"},
    )

    assert law["title"] == "Test Law"
    assert law["status"] == "DRAFT"
    assert law["reversibility_class"] == "REVERSIBLE"

    # Activate
    activated_law = ftl.activate_law(law["law_id"])
    assert activated_law["status"] == "ACTIVE"
    assert activated_law["next_checkpoint_at"] is not None


def test_ftl_list_laws(tmp_path):
    """Test listing laws"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")

    law1 = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Law 1",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    law2 = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Law 2",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )

    # List all
    all_laws = ftl.list_laws()
    assert len(all_laws) == 2

    # List by status
    draft_laws = ftl.list_laws(status="DRAFT")
    assert len(draft_laws) == 2


def test_ftl_complete_review(tmp_path):
    """Test completing a law review"""
    db_path = tmp_path / "test.db"
    time_provider = TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))
    ftl = FTL(str(db_path), time_provider=time_provider)

    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    # Advance time and trigger review
    time_provider.advance_days(35)
    ftl.tick()

    # Complete review
    reviewed_law = ftl.complete_review(
        law_id=law["law_id"], outcome="continue", notes="Looks good"
    )

    assert reviewed_law["status"] == "ACTIVE"


def test_ftl_tick_healthy_system(tmp_path):
    """Test tick on healthy system"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    ftl.delegate("alice", workspace["workspace_id"], "bob", 180)

    result = ftl.tick()

    assert result.freedom_health.risk_level == RiskLevel.GREEN
    assert not result.has_warnings()
    assert not result.has_halts()


def test_ftl_health(tmp_path):
    """Test health status"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    ftl.delegate("alice", workspace["workspace_id"], "bob", 180)

    health = ftl.health()

    assert health.risk_level == RiskLevel.GREEN
    assert health.concentration.total_active_delegations == 1
    assert health.law_review_health.total_active_laws == 0


def test_ftl_get_safety_events(tmp_path):
    """Test getting safety events"""
    db_path = tmp_path / "test.db"
    time_provider = TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))
    ftl = FTL(str(db_path), time_provider=time_provider)

    # Initially no events
    events = ftl.get_safety_events()
    assert len(events) == 0

    # Create a law and advance time to trigger review
    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    # Advance time past checkpoint
    time_provider.advance_days(35)

    # Run tick - should trigger review
    ftl.tick()

    # Should have LawReviewTriggered event
    events = ftl.get_safety_events()
    assert len(events) > 0
    assert any(e["event_type"] == "LawReviewTriggered" for e in events)


def test_ftl_get_safety_policy(tmp_path):
    """Test getting safety policy"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    policy = ftl.get_safety_policy()

    assert policy.delegation_gini_warn == 0.55
    assert policy.delegation_gini_halt == 0.70
    assert policy.max_delegation_ttl_days == 365
