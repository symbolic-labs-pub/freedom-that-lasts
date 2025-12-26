"""
Base Command model for CQRS pattern

Commands represent intentions to change the system state.
They are validated, then converted to events by command handlers.

Fun fact: CQRS (Command Query Responsibility Segregation) was formalized
by Greg Young around 2010, but the concept dates back to Bertrand Meyer's
"Command-Query Separation" principle from 1988!
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Command(BaseModel):
    """
    Base command class - all domain commands inherit from this

    Commands express intent to change the system. They are:
    - Validated before execution (invariants checked)
    - Idempotent (same command_id = same result)
    - Converted to events by handlers
    - Never stored directly (only the resulting events persist)

    The command_id ensures idempotency: executing the same command
    twice produces the same events and has no additional effect.
    """

    command_id: str = Field(
        ...,
        description="Unique command identifier (idempotency key)",
    )

    command_type: str = Field(
        ...,
        description="Type of command: 'CreateWorkspace', 'DelegateDecisionRight', etc.",
    )

    actor_id: str | None = Field(
        default=None,
        description="ID of actor issuing this command (None for system commands)",
    )

    issued_at: datetime = Field(
        ...,
        description="UTC timestamp when command was issued",
    )

    payload: dict = Field(
        default_factory=dict,
        description="Command-specific parameters (must be JSON-serializable)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "command_id": "cmd-123",
                    "command_type": "CreateWorkspace",
                    "actor_id": "user-alice",
                    "issued_at": "2025-01-15T10:30:00Z",
                    "payload": {
                        "name": "Health",
                        "parent_workspace_id": None,
                        "scope": {"territory": "Budapest"},
                    },
                }
            ]
        }
    }


def create_command(
    *,
    command_id: str,
    command_type: str,
    issued_at: datetime,
    actor_id: str | None = None,
    payload: dict | None = None,
) -> Command:
    """
    Factory function for creating commands with all required fields

    This provides a clean way to construct commands with named parameters
    and ensures all required fields are provided.
    """
    return Command(
        command_id=command_id,
        command_type=command_type,
        actor_id=actor_id,
        issued_at=issued_at,
        payload=payload or {},
    )
