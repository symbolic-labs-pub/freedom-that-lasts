"""
Tests for feedback module projections

Tests event-sourced read models for system health monitoring.
Projections track health scores and safety event history.

Fun fact: Health monitoring in distributed systems dates back to the 1970s
with ARPANET's early network monitoring tools - the first "system health checks"!
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.feedback.models import (
    ConcentrationMetrics,
    FreedomHealthScore,
    LawReviewHealth,
    RiskLevel,
)
from freedom_that_lasts.feedback.projections import FreedomHealthProjection, SafetyEventLog
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id


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
# FreedomHealthProjection Tests
# =============================================================================


def test_freedom_health_projection_initial_state():
    """Test projection starts with no health data"""
    projection = FreedomHealthProjection()
    assert projection.current_health is None
    assert projection.last_updated is None
    assert projection.get() is None


def test_freedom_health_projection_system_tick_updates_timestamp(test_time):
    """Test SystemTick event updates last_updated timestamp"""
    projection = FreedomHealthProjection()

    event = create_event(
        event_id=generate_id(),
        stream_id="system",
        stream_type="System",
        event_type="SystemTick",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={"tick_id": "tick-1"},
        version=1,
    )

    projection.apply_event(event)

    assert projection.last_updated == test_time.now()
    assert projection.current_health is None  # Health not computed yet


def test_freedom_health_projection_update_health(test_time):
    """Test update_health sets current health and timestamp"""
    projection = FreedomHealthProjection()

    health = FreedomHealthScore(
        risk_level=RiskLevel.GREEN,
        concentration=ConcentrationMetrics(
            gini_coefficient=0.15,
            max_in_degree=2,
            total_active_delegations=5,
            unique_delegates=3,
        ),
        law_review_health=LawReviewHealth(
            total_active_laws=5,
            overdue_reviews=0,
            upcoming_reviews_7d=1,
            upcoming_reviews_30d=2,
        ),
        computed_at=test_time.now(),
    )

    projection.update_health(health)

    assert projection.current_health == health
    assert projection.last_updated == test_time.now()
    assert projection.get() == health


def test_freedom_health_projection_get_returns_none_initially():
    """Test get() returns None when no health computed"""
    projection = FreedomHealthProjection()
    assert projection.get() is None


def test_freedom_health_projection_serialization_with_health(test_time):
    """Test to_dict() and from_dict() with health data"""
    projection = FreedomHealthProjection()

    health = FreedomHealthScore(
        risk_level=RiskLevel.YELLOW,
        concentration=ConcentrationMetrics(
            gini_coefficient=0.35,
            max_in_degree=5,
            total_active_delegations=10,
            unique_delegates=4,
        ),
        law_review_health=LawReviewHealth(
            total_active_laws=10,
            overdue_reviews=2,
            upcoming_reviews_7d=3,
            upcoming_reviews_30d=5,
        ),
        computed_at=test_time.now(),
    )

    projection.update_health(health)

    # Serialize
    data = projection.to_dict()
    assert data["current_health"] is not None
    assert data["last_updated"] is not None

    # Deserialize
    restored = FreedomHealthProjection.from_dict(data)
    assert restored.current_health is not None
    assert restored.current_health.risk_level == RiskLevel.YELLOW
    assert restored.last_updated == test_time.now()


def test_freedom_health_projection_serialization_empty():
    """Test to_dict() and from_dict() with no data"""
    projection = FreedomHealthProjection()

    # Serialize empty projection
    data = projection.to_dict()
    assert data["current_health"] is None
    assert data["last_updated"] is None

    # Deserialize empty data
    restored = FreedomHealthProjection.from_dict(data)
    assert restored.current_health is None
    assert restored.last_updated is None


def test_freedom_health_projection_from_dict_partial_data():
    """Test from_dict() with partial data (only health, no timestamp)"""
    data = {
        "current_health": {
            "risk_level": "GREEN",
            "concentration": {
                "gini_coefficient": 0.1,
                "max_in_degree": 1,
                "total_active_delegations": 3,
                "unique_delegates": 2,
            },
            "law_review_health": {
                "total_active_laws": 5,
                "overdue_reviews": 0,
                "upcoming_reviews_7d": 0,
                "upcoming_reviews_30d": 1,
            },
            "reasons": [],
            "computed_at": datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        },
        "last_updated": None,
    }

    projection = FreedomHealthProjection.from_dict(data)
    assert projection.current_health is not None
    assert projection.current_health.risk_level == RiskLevel.GREEN
    assert projection.last_updated is None


def test_freedom_health_projection_from_dict_only_timestamp():
    """Test from_dict() with only timestamp (no health)"""
    data = {
        "current_health": None,
        "last_updated": datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
    }

    projection = FreedomHealthProjection.from_dict(data)
    assert projection.current_health is None
    assert projection.last_updated == datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# =============================================================================
# SafetyEventLog Tests
# =============================================================================


def test_safety_event_log_initial_state():
    """Test log starts empty"""
    log = SafetyEventLog()
    assert log.events == []
    assert log.get_recent() == []
    assert log.count_by_type() == {}


def test_safety_event_log_tracks_safety_events(test_time):
    """Test safety events are tracked in the log"""
    log = SafetyEventLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="delegation-1",
        stream_type="Delegation",
        event_type="DelegationConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "delegation_id": "del-1",
            "concentration_level": 0.35,
        },
        version=1,
    )

    log.apply_event(event)

    assert len(log.events) == 1
    assert log.events[0]["event_type"] == "DelegationConcentrationWarning"
    assert log.events[0]["payload"]["delegation_id"] == "del-1"


def test_safety_event_log_ignores_non_safety_events(test_time):
    """Test non-safety events are not tracked"""
    log = SafetyEventLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="law-1",
        stream_type="Law",
        event_type="LawCreated",  # Not a safety event
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={"law_id": "law-1"},
        version=1,
    )

    log.apply_event(event)

    assert len(log.events) == 0


def test_safety_event_log_tracks_multiple_event_types(test_time):
    """Test multiple safety event types are tracked"""
    log = SafetyEventLog()

    # Add different types of safety events
    event_types = [
        "DelegationConcentrationWarning",
        "DelegationConcentrationHalt",
        "TransparencyEscalated",
        "LawReviewTriggered",
    ]

    for i, event_type in enumerate(event_types):
        event = create_event(
            event_id=generate_id(),
            stream_id=f"stream-{i}",
            stream_type="System",
            event_type=event_type,
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="system",
            payload={"index": i},
            version=1,
        )
        log.apply_event(event)

    assert len(log.events) == 4
    assert set(e["event_type"] for e in log.events) == set(event_types)


def test_safety_event_log_get_recent_with_limit(test_time):
    """Test get_recent returns limited number of events"""
    log = SafetyEventLog()

    # Add 10 events
    for i in range(10):
        event = create_event(
            event_id=generate_id(),
            stream_id=f"stream-{i}",
            stream_type="System",
            event_type="DelegationConcentrationWarning",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="system",
            payload={"index": i},
            version=1,
        )
        log.apply_event(event)

    recent = log.get_recent(limit=5)
    assert len(recent) == 5


def test_safety_event_log_get_recent_sorts_by_time(test_time):
    """Test get_recent returns events sorted by time (newest first)"""
    log = SafetyEventLog()
    from datetime import timedelta

    # Add events with different timestamps
    times = [
        test_time.now(),
        test_time.now() + timedelta(seconds=10),
        test_time.now() + timedelta(seconds=5),
    ]

    for i, time in enumerate(times):
        event = create_event(
            event_id=generate_id(),
            stream_id=f"stream-{i}",
            stream_type="System",
            event_type="DelegationConcentrationWarning",
            occurred_at=time,
            command_id=generate_id(),
            actor_id="system",
            payload={"index": i},
            version=1,
        )
        log.apply_event(event)

    recent = log.get_recent()

    # Should be sorted newest first
    assert recent[0]["payload"]["index"] == 1  # +10 seconds
    assert recent[1]["payload"]["index"] == 2  # +5 seconds
    assert recent[2]["payload"]["index"] == 0  # now


def test_safety_event_log_get_by_type(test_time):
    """Test get_by_type filters events by type"""
    log = SafetyEventLog()

    # Add warning and halt events
    for i in range(3):
        event_type = "DelegationConcentrationWarning" if i < 2 else "DelegationConcentrationHalt"
        event = create_event(
            event_id=generate_id(),
            stream_id=f"stream-{i}",
            stream_type="System",
            event_type=event_type,
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="system",
            payload={"index": i},
            version=1,
        )
        log.apply_event(event)

    warnings = log.get_by_type("DelegationConcentrationWarning")
    halts = log.get_by_type("DelegationConcentrationHalt")

    assert len(warnings) == 2
    assert len(halts) == 1


def test_safety_event_log_get_by_type_nonexistent(test_time):
    """Test get_by_type returns empty list for non-existent type"""
    log = SafetyEventLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="stream-1",
        stream_type="System",
        event_type="DelegationConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={},
        version=1,
    )
    log.apply_event(event)

    result = log.get_by_type("NonExistentType")
    assert result == []


def test_safety_event_log_count_by_type(test_time):
    """Test count_by_type returns correct counts"""
    log = SafetyEventLog()

    # Add 2 warnings, 1 halt, 3 reviews
    event_counts = {
        "DelegationConcentrationWarning": 2,
        "DelegationConcentrationHalt": 1,
        "LawReviewTriggered": 3,
    }

    for event_type, count in event_counts.items():
        for i in range(count):
            event = create_event(
                event_id=generate_id(),
                stream_id=f"stream-{event_type}-{i}",
                stream_type="System",
                event_type=event_type,
                occurred_at=test_time.now(),
                command_id=generate_id(),
                actor_id="system",
                payload={"index": i},
                version=1,
            )
            log.apply_event(event)

    counts = log.count_by_type()
    assert counts == event_counts


def test_safety_event_log_count_by_type_empty():
    """Test count_by_type returns empty dict for empty log"""
    log = SafetyEventLog()
    counts = log.count_by_type()
    assert counts == {}


def test_safety_event_log_serialization(test_time):
    """Test to_dict() and from_dict() preserve events"""
    log = SafetyEventLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="stream-1",
        stream_type="System",
        event_type="DelegationConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={"test": "data"},
        version=1,
    )
    log.apply_event(event)

    # Serialize
    data = log.to_dict()
    assert len(data["events"]) == 1

    # Deserialize
    restored = SafetyEventLog.from_dict(data)
    assert len(restored.events) == 1
    assert restored.events[0]["event_type"] == "DelegationConcentrationWarning"
    assert restored.events[0]["payload"]["test"] == "data"


def test_safety_event_log_serialization_empty():
    """Test to_dict() and from_dict() with empty log"""
    log = SafetyEventLog()

    # Serialize empty log
    data = log.to_dict()
    assert data["events"] == []

    # Deserialize empty data
    restored = SafetyEventLog.from_dict(data)
    assert restored.events == []
