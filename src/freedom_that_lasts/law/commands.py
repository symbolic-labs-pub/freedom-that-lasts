"""
Law Module Commands - Intentions to change governance state

Commands represent what users want to do. They are validated
against invariants and converted to events by handlers.

Fun fact: Commands can fail (invariant violations), but events
never fail - they're facts that already happened!
"""

from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.law.models import ReversibilityClass


# Workspace Commands


class CreateWorkspace(BaseModel):
    """
    Create a new workspace (governance scope)

    Workspaces can be nested to create hierarchical authority structures.
    """

    name: str = Field(..., min_length=1, max_length=200)
    parent_workspace_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class ArchiveWorkspace(BaseModel):
    """Archive a workspace (make it inactive)"""

    workspace_id: str
    reason: str = Field(..., min_length=1)


# Delegation Commands


class DelegateDecisionRight(BaseModel):
    """
    Delegate decision authority to another actor

    Creates an edge in the delegation DAG, subject to:
    - TTL must be <= policy maximum
    - Must not create a cycle in the delegation graph
    - Workspace must exist
    """

    from_actor: str = Field(..., min_length=1)
    workspace_id: str
    to_actor: str = Field(..., min_length=1)
    ttl_days: int = Field(..., ge=1, le=3650)
    visibility: str | None = None  # Defaults to policy setting
    renewable: bool = True
    purpose_tag: str | None = None


class RenewDelegation(BaseModel):
    """Extend the TTL of an existing delegation"""

    delegation_id: str
    ttl_days: int = Field(..., ge=1, le=3650)


class RevokeDelegation(BaseModel):
    """Cancel a delegation (make it inactive immediately)"""

    delegation_id: str
    reason: str | None = None


# Law Lifecycle Commands


class CreateLaw(BaseModel):
    """
    Create a new law in DRAFT status

    Laws must have:
    - Reversibility classification (affects safeguards)
    - Checkpoint schedule (mandatory review points)
    - Explicit scope (where/when it applies)
    """

    workspace_id: str
    title: str = Field(..., min_length=1, max_length=500)
    scope: dict[str, Any] = Field(default_factory=dict)
    reversibility_class: ReversibilityClass
    checkpoints: list[int] = Field(
        ...,
        min_length=1,
        description="Days after activation when reviews are mandatory",
    )
    params: dict[str, Any] = Field(default_factory=dict)


class ActivateLaw(BaseModel):
    """
    Move a law from DRAFT to ACTIVE

    Activation:
    - Starts the checkpoint clock
    - Makes the law enforceable
    - Requires checkpoint schedule validation
    """

    law_id: str


class TriggerLawReview(BaseModel):
    """
    Initiate a law review (manual or system-triggered)

    Reviews can be triggered:
    - Manually by authorized actors
    - Automatically when checkpoints are overdue
    - Automatically on threshold breaches
    """

    law_id: str
    reason: str = Field(..., min_length=1)


class CompleteLawReview(BaseModel):
    """Complete a law review with outcome"""

    law_id: str
    outcome: str = Field(
        ..., pattern="^(continue|adjust|sunset)$"
    )  # "continue" | "adjust" | "sunset"
    notes: str | None = None


class AdjustLaw(BaseModel):
    """Modify a law based on review feedback"""

    law_id: str
    changes: dict[str, Any] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ScheduleLawSunset(BaseModel):
    """Schedule a law for termination"""

    law_id: str
    sunset_days: int = Field(..., ge=0)  # Days from now
    reason: str = Field(..., min_length=1)


class ArchiveLaw(BaseModel):
    """Archive a law (final state, preserved for record)"""

    law_id: str
    reason: str = Field(..., min_length=1)


# Command type mappings for handlers

LAW_COMMAND_TYPES = {
    "CreateWorkspace": CreateWorkspace,
    "ArchiveWorkspace": ArchiveWorkspace,
    "DelegateDecisionRight": DelegateDecisionRight,
    "RenewDelegation": RenewDelegation,
    "RevokeDelegation": RevokeDelegation,
    "CreateLaw": CreateLaw,
    "ActivateLaw": ActivateLaw,
    "TriggerLawReview": TriggerLawReview,
    "CompleteLawReview": CompleteLawReview,
    "AdjustLaw": AdjustLaw,
    "ScheduleLawSunset": ScheduleLawSunset,
    "ArchiveLaw": ArchiveLaw,
}
