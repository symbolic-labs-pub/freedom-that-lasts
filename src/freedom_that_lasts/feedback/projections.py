"""
Feedback Module Projections - Health and safety state views

These projections maintain the current state of system health indicators
and safety events.
"""

from datetime import datetime
from typing import Any

from freedom_that_lasts.feedback.models import FreedomHealthScore, RiskLevel
from freedom_that_lasts.kernel.events import Event


class FreedomHealthProjection:
    """
    Projection: Current FreedomHealth scorecard

    Maintains the most recent health assessment of the system.
    Updated on SystemTick events and concentration/review triggers.
    """

    def __init__(self) -> None:
        self.current_health: FreedomHealthScore | None = None
        self.last_updated: datetime | None = None

    def apply_event(self, event: Event) -> None:
        """Apply an event to update projection state"""
        # This projection is computed on-demand rather than event-sourced
        # We just track when it was last computed
        if event.event_type == "SystemTick":
            self.last_updated = event.occurred_at

    def update_health(self, health: FreedomHealthScore) -> None:
        """Update the current health scorecard"""
        self.current_health = health
        self.last_updated = health.computed_at

    def get(self) -> FreedomHealthScore | None:
        """Get current health scorecard"""
        return self.current_health

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "current_health": (
                self.current_health.model_dump() if self.current_health else None
            ),
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FreedomHealthProjection":
        """Deserialize from dict"""
        projection = cls()
        if data.get("current_health"):
            projection.current_health = FreedomHealthScore(**data["current_health"])
        if data.get("last_updated"):
            projection.last_updated = datetime.fromisoformat(data["last_updated"])
        return projection


class SafetyEventLog:
    """
    Projection: Log of all safety events (warnings, halts, escalations)

    Maintains a queryable history of automatic safety responses.
    This is critical for auditing and understanding system behavior.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def apply_event(self, event: Event) -> None:
        """Apply an event to update projection state"""
        # Track all feedback/safety events
        if event.event_type in [
            "DelegationConcentrationWarning",
            "DelegationConcentrationHalt",
            "TransparencyEscalated",
            "LawReviewTriggered",
        ]:
            self.events.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at,
                    "payload": event.payload,
                }
            )

    def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get most recent safety events"""
        return sorted(
            self.events,
            key=lambda e: (
                e["occurred_at"]
                if isinstance(e["occurred_at"], datetime)
                else datetime.fromisoformat(e["occurred_at"])
            ),
            reverse=True,
        )[:limit]

    def get_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type"""
        return [e for e in self.events if e["event_type"] == event_type]

    def count_by_type(self) -> dict[str, int]:
        """Count events by type"""
        counts: dict[str, int] = {}
        for event in self.events:
            event_type = event["event_type"]
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {"events": self.events}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SafetyEventLog":
        """Deserialize from dict"""
        log = cls()
        log.events = data.get("events", [])
        return log
