"""
Tests for law module models

Tests domain models including Delegation and Law business logic methods.
These models form the core of the constitutional governance system.

Fun fact: The concept of "delegation" in governance dates back to the Roman Republic,
where the Senate would delegate imperium (command authority) to magistrates for
specific purposes and time periods - much like our TTL-based delegation system!
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.law.models import (
    Delegation,
    Law,
    LawStatus,
    ReversibilityClass,
)


# =============================================================================
# Delegation Model Tests
# =============================================================================


def test_delegation_is_active_when_not_revoked_and_not_expired(test_time):
    """Test delegation is active when not revoked and before expiry"""
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now(),
        ttl_days=30,
        expires_at=test_time.now() + timedelta(days=30),
        renewable=True,
        visibility="private",
    )

    assert delegation.is_active(test_time.now()) is True


def test_delegation_is_inactive_when_revoked(test_time):
    """Test delegation is inactive when revoked"""
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now(),
        ttl_days=30,
        expires_at=test_time.now() + timedelta(days=30),
        renewable=True,
        visibility="private",
        revoked_at=test_time.now(),  # Revoked now
    )

    assert delegation.is_active(test_time.now()) is False


def test_delegation_is_inactive_when_expired(test_time):
    """Test delegation is inactive when expired"""
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now() - timedelta(days=31),
        ttl_days=30,
        expires_at=test_time.now() - timedelta(days=1),  # Expired yesterday
        renewable=True,
        visibility="private",
    )

    assert delegation.is_active(test_time.now()) is False


def test_delegation_is_inactive_when_exactly_at_expiry(test_time):
    """Test delegation is inactive at exact expiry time"""
    expiry_time = test_time.now()
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now() - timedelta(days=30),
        ttl_days=30,
        expires_at=expiry_time,
        renewable=True,
        visibility="private",
    )

    # At exact expiry time, delegation should be inactive (>= check)
    assert delegation.is_active(expiry_time) is False


def test_delegation_days_until_expiry_positive(test_time):
    """Test days_until_expiry returns positive days for future expiry"""
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now(),
        ttl_days=15,
        expires_at=test_time.now() + timedelta(days=15),
        renewable=True,
        visibility="private",
    )

    assert delegation.days_until_expiry(test_time.now()) == 15


def test_delegation_days_until_expiry_negative(test_time):
    """Test days_until_expiry returns negative days for past expiry"""
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now() - timedelta(days=40),
        ttl_days=30,
        expires_at=test_time.now() - timedelta(days=10),  # Expired 10 days ago
        renewable=True,
        visibility="private",
    )

    assert delegation.days_until_expiry(test_time.now()) == -10


def test_delegation_days_until_expiry_zero(test_time):
    """Test days_until_expiry returns 0 for same-day expiry"""
    # Create delegation that expires in less than 24 hours
    delegation = Delegation(
        delegation_id="del-1",
        workspace_id="ws-1",
        from_actor="alice",
        to_actor="bob",
        delegated_at=test_time.now(),
        ttl_days=1,
        expires_at=test_time.now() + timedelta(hours=12),  # 12 hours from now
        renewable=True,
        visibility="private",
    )

    # timedelta.days truncates to 0 for < 24 hours
    assert delegation.days_until_expiry(test_time.now()) == 0


# =============================================================================
# Law Model Tests
# =============================================================================


def test_law_is_active_when_status_active(test_time):
    """Test law is_active returns True when status is ACTIVE"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ACTIVE,
        created_at=test_time.now(),
    )

    assert law.is_active() is True


def test_law_is_not_active_when_status_draft(test_time):
    """Test law is_active returns False when status is DRAFT"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.DRAFT,
        created_at=test_time.now(),
    )

    assert law.is_active() is False


def test_law_is_not_active_when_status_review(test_time):
    """Test law is_active returns False when status is REVIEW"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.REVIEW,
        created_at=test_time.now(),
    )

    assert law.is_active() is False


def test_law_is_not_active_when_status_archived(test_time):
    """Test law is_active returns False when status is ARCHIVED"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ARCHIVED,
        created_at=test_time.now(),
    )

    assert law.is_active() is False


def test_law_is_review_overdue_when_checkpoint_passed(test_time):
    """Test is_review_overdue returns True when checkpoint has passed"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ACTIVE,
        created_at=test_time.now(),
        activated_at=test_time.now(),
        next_checkpoint_at=test_time.now() - timedelta(days=5),  # 5 days overdue
    )

    assert law.is_review_overdue(test_time.now()) is True


def test_law_is_not_review_overdue_when_checkpoint_future(test_time):
    """Test is_review_overdue returns False when checkpoint is in future"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ACTIVE,
        created_at=test_time.now(),
        activated_at=test_time.now(),
        next_checkpoint_at=test_time.now() + timedelta(days=15),  # 15 days away
    )

    assert law.is_review_overdue(test_time.now()) is False


def test_law_is_not_review_overdue_when_no_checkpoint(test_time):
    """Test is_review_overdue returns False when next_checkpoint_at is None"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.DRAFT,
        created_at=test_time.now(),
        next_checkpoint_at=None,  # No checkpoint scheduled
    )

    assert law.is_review_overdue(test_time.now()) is False


def test_law_days_until_checkpoint_positive(test_time):
    """Test days_until_checkpoint returns positive days for future checkpoint"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ACTIVE,
        created_at=test_time.now(),
        activated_at=test_time.now(),
        next_checkpoint_at=test_time.now() + timedelta(days=25),
    )

    assert law.days_until_checkpoint(test_time.now()) == 25


def test_law_days_until_checkpoint_negative(test_time):
    """Test days_until_checkpoint returns negative days for overdue checkpoint"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.ACTIVE,
        created_at=test_time.now(),
        activated_at=test_time.now(),
        next_checkpoint_at=test_time.now() - timedelta(days=10),  # 10 days overdue
    )

    assert law.days_until_checkpoint(test_time.now()) == -10


def test_law_days_until_checkpoint_none_when_no_checkpoint(test_time):
    """Test days_until_checkpoint returns None when next_checkpoint_at is None"""
    law = Law(
        law_id="law-1",
        workspace_id="ws-1",
        title="Test Law",
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180],
        status=LawStatus.DRAFT,
        created_at=test_time.now(),
        next_checkpoint_at=None,  # No checkpoint scheduled
    )

    assert law.days_until_checkpoint(test_time.now()) is None


def test_delegation_creation_with_all_fields(test_time):
    """Test creating delegation with all optional fields"""
    delegation = Delegation(
        delegation_id="del-complex",
        workspace_id="ws-health",
        from_actor="manager-1",
        to_actor="specialist-2",
        delegated_at=test_time.now(),
        ttl_days=90,
        expires_at=test_time.now() + timedelta(days=90),
        renewable=False,
        visibility="public",
        purpose_tag="medical_expert",
        revoked_at=None,
    )

    assert delegation.delegation_id == "del-complex"
    assert delegation.renewable is False
    assert delegation.visibility == "public"
    assert delegation.purpose_tag == "medical_expert"


def test_law_creation_with_metadata(test_time):
    """Test creating law with full metadata"""
    law = Law(
        law_id="law-pilot",
        workspace_id="ws-budapest",
        title="Healthcare Pilot Program",
        scope={"territory": "District5", "population": 50000},
        reversibility_class=ReversibilityClass.SEMI_REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={"max_wait_days": 10, "coverage_target": 0.95},
        status=LawStatus.DRAFT,
        created_at=test_time.now(),
        metadata={"author": "alice", "version": 1, "tags": ["pilot", "healthcare"]},
    )

    assert law.reversibility_class == ReversibilityClass.SEMI_REVERSIBLE
    assert law.scope["territory"] == "District5"
    assert law.params["coverage_target"] == 0.95
    assert law.metadata["author"] == "alice"
