"""
Base Event model for event sourcing

Events are immutable facts about what happened in the system.
They form an append-only log that serves as the source of truth.

Fun fact: In event sourcing, the event log is like a time machine -
you can replay history to any point and see exactly what the system
state was at that moment!
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Event(BaseModel):
    """
    Base event class - all domain events inherit from this

    Events are the fundamental unit of change in the system. They are:
    - Immutable (never modified after creation)
    - Append-only (never deleted)
    - Timestamped (preserve temporal ordering)
    - Versioned (track stream evolution)
    - Replayable (deterministic state reconstruction)

    The combination of stream_id + version provides optimistic locking,
    while command_id ensures idempotency.
    """

    event_id: str = Field(
        ...,
        description="Unique event identifier (UUIDv7 for time-ordering)",
    )

    stream_id: str = Field(
        ...,
        description="Aggregate root identifier - groups related events",
    )

    stream_type: str = Field(
        ...,
        description="Type of aggregate: 'workspace', 'law', 'delegation', etc.",
    )

    event_type: str = Field(
        ...,
        description="Specific event type: 'WorkspaceCreated', 'LawActivated', etc.",
    )

    occurred_at: datetime = Field(
        ...,
        description="UTC timestamp when event occurred",
    )

    actor_id: str | None = Field(
        default=None,
        description="ID of actor who triggered this event (None for system events)",
    )

    command_id: str = Field(
        ...,
        description="ID of command that caused this event (idempotency key)",
    )

    payload: dict = Field(
        default_factory=dict,
        description="Event-specific data (must be JSON-serializable)",
    )

    version: int = Field(
        ...,
        description="Stream version after this event (monotonically increasing)",
        ge=1,
    )

    model_config = {
        "frozen": True,  # Events are immutable
        "json_schema_extra": {
            "examples": [
                {
                    "event_id": "01908e9a-3b87-7000-8000-123456789abc",
                    "stream_id": "workspace-001",
                    "stream_type": "workspace",
                    "event_type": "WorkspaceCreated",
                    "occurred_at": "2025-01-15T10:30:00Z",
                    "actor_id": "user-alice",
                    "command_id": "cmd-123",
                    "payload": {"name": "Health", "scope": {"territory": "Budapest"}},
                    "version": 1,
                }
            ]
        },
    }


def create_event(
    *,
    event_id: str,
    stream_id: str,
    stream_type: str,
    event_type: str,
    occurred_at: datetime,
    command_id: str,
    version: int,
    actor_id: str | None = None,
    payload: dict | None = None,
) -> Event:
    """
    Factory function for creating events with all required fields

    This provides a clean way to construct events with named parameters
    and ensures all required fields are provided.
    """
    return Event(
        event_id=event_id,
        stream_id=stream_id,
        stream_type=stream_type,
        event_type=event_type,
        occurred_at=occurred_at,
        actor_id=actor_id,
        command_id=command_id,
        payload=payload or {},
        version=version,
    )
