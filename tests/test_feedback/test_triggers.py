"""
Tests for Feedback Triggers - Automatic reflex events

These tests verify that triggers correctly detect dangerous conditions
and emit appropriate reflex events (warnings, halts, escalations).
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.feedback.triggers import (
    evaluate_all_triggers,
    evaluate_delegation_concentration_trigger,
    evaluate_law_review_trigger,
)
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider


def test_delegation_concentration_trigger_no_events() -> None:
    """Test trigger with healthy concentration - no events"""
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Low concentration - well below thresholds
    in_degree_map = {"alice": 10, "bob": 12, "charlie": 11}

    events = evaluate_delegation_concentration_trigger(in_degree_map, policy, now)

    assert len(events) == 0


def test_delegation_concentration_trigger_warning() -> None:
    """Test trigger emits warning when threshold breached"""
    policy = SafetyPolicy(
        delegation_gini_warn=0.5,
        delegation_gini_halt=0.7,
    )
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Moderate concentration that triggers warning but not halt
    in_degree_map = {"alice": 5, "bob": 10, "charlie": 50, "dave": 3}

    events = evaluate_delegation_concentration_trigger(in_degree_map, policy, now)

    assert len(events) == 1
    assert events[0].event_type == "DelegationConcentrationWarning"
    payload = events[0].payload
    assert payload["gini_coefficient"] >= policy.delegation_gini_warn
    assert payload["gini_coefficient"] < policy.delegation_gini_halt


def test_delegation_concentration_trigger_halt() -> None:
    """Test trigger emits halt when threshold breached"""
    policy = SafetyPolicy(
        delegation_gini_halt=0.6,
        transparency_escalation_on_halt=True,
    )
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Extreme concentration that triggers halt
    in_degree_map = {"alice": 2, "bob": 3, "charlie": 100}

    events = evaluate_delegation_concentration_trigger(in_degree_map, policy, now)

    # Should emit halt + transparency escalation
    assert len(events) == 2

    halt_event = events[0]
    assert halt_event.event_type == "DelegationConcentrationHalt"
    assert halt_event.payload["gini_coefficient"] >= policy.delegation_gini_halt
    assert "transparency_escalated" in halt_event.payload["automatic_responses"]

    transparency_event = events[1]
    assert transparency_event.event_type == "TransparencyEscalated"
    assert transparency_event.payload["new_level"] == "aggregate_plus"


def test_delegation_concentration_trigger_in_degree_halt() -> None:
    """Test trigger emits halt when in-degree threshold breached"""
    policy = SafetyPolicy(
        delegation_in_degree_halt=50,
        transparency_escalation_on_halt=True,
    )
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # One actor has extreme in-degree
    in_degree_map = {"alice": 5, "bob": 60, "charlie": 10}

    events = evaluate_delegation_concentration_trigger(in_degree_map, policy, now)

    assert len(events) == 2
    halt_event = events[0]
    assert halt_event.event_type == "DelegationConcentrationHalt"
    assert halt_event.payload["max_in_degree"] >= policy.delegation_in_degree_halt


def test_delegation_concentration_trigger_no_escalation() -> None:
    """Test halt without transparency escalation when disabled"""
    policy = SafetyPolicy(
        delegation_gini_halt=0.4,  # Lower threshold
        transparency_escalation_on_halt=False,
    )
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Extreme concentration (Gini ~0.48)
    in_degree_map = {"alice": 2, "bob": 100}

    events = evaluate_delegation_concentration_trigger(in_degree_map, policy, now)

    # Should only emit halt, no transparency escalation
    assert len(events) == 1
    assert events[0].event_type == "DelegationConcentrationHalt"
    assert events[0].payload["automatic_responses"] == []


def test_law_review_trigger_no_overdue() -> None:
    """Test law review trigger with no overdue laws"""
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    overdue_laws = []

    events = evaluate_law_review_trigger(overdue_laws, now)

    assert len(events) == 0


def test_law_review_trigger_overdue_laws() -> None:
    """Test law review trigger with overdue laws"""
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Three laws with overdue checkpoints
    overdue_laws = [
        {
            "law_id": "law-1",
            "status": "ACTIVE",
            "next_checkpoint_at": now - timedelta(days=5),
            "version": 3,
        },
        {
            "law_id": "law-2",
            "status": "ACTIVE",
            "next_checkpoint_at": now - timedelta(days=10),
            "version": 2,
        },
        {
            "law_id": "law-3",
            "status": "ACTIVE",
            "next_checkpoint_at": now - timedelta(days=2),
            "version": 1,
        },
    ]

    events = evaluate_law_review_trigger(overdue_laws, now)

    assert len(events) == 3
    for event in events:
        assert event.event_type == "LawReviewTriggered"
        assert event.payload["reason"] == "checkpoint_overdue"


def test_law_review_trigger_skips_already_in_review() -> None:
    """Test law review trigger skips laws already in REVIEW status"""
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # One law overdue but already in review
    overdue_laws = [
        {
            "law_id": "law-1",
            "status": "REVIEW",  # Already in review
            "next_checkpoint_at": now - timedelta(days=5),
            "version": 3,
        },
        {
            "law_id": "law-2",
            "status": "ACTIVE",  # Not in review yet
            "next_checkpoint_at": now - timedelta(days=10),
            "version": 2,
        },
    ]

    events = evaluate_law_review_trigger(overdue_laws, now)

    # Should only trigger for law-2
    assert len(events) == 1
    assert events[0].payload["law_id"] == "law-2"


def test_evaluate_all_triggers() -> None:
    """Test complete trigger evaluation"""
    policy = SafetyPolicy(
        delegation_gini_warn=0.4,  # Lower threshold to trigger warning
        delegation_gini_halt=0.7,
    )
    time_provider = TestTimeProvider(
        datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    )
    now = time_provider.now()

    # Moderate concentration (warning level) - Gini ~0.42
    in_degree_map = {"alice": 5, "bob": 10, "charlie": 40}

    # Two overdue laws
    overdue_laws = [
        {
            "law_id": "law-1",
            "status": "ACTIVE",
            "next_checkpoint_at": now - timedelta(days=5),
            "version": 3,
        },
        {
            "law_id": "law-2",
            "status": "ACTIVE",
            "next_checkpoint_at": now - timedelta(days=10),
            "version": 2,
        },
    ]

    events = evaluate_all_triggers(
        in_degree_map=in_degree_map,
        overdue_laws=overdue_laws,
        policy=policy,
        time_provider=time_provider,
    )

    # Should get: 1 concentration warning + 2 law review triggers
    assert len(events) == 3

    concentration_events = [
        e for e in events if e.event_type == "DelegationConcentrationWarning"
    ]
    review_events = [e for e in events if e.event_type == "LawReviewTriggered"]

    assert len(concentration_events) == 1
    assert len(review_events) == 2
