"""
Law Module Events - Domain events for governance

Events are immutable facts about what happened. They form the
append-only log that is the source of truth for the law module.

Fun fact: In event sourcing, events are named in past tense because
they represent facts that already happened, not intentions!
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.law.models import LawStatus, ReversibilityClass


# Workspace Events


class WorkspaceCreated(BaseModel):
    """A new workspace was created"""

    workspace_id: str
    name: str
    parent_workspace_id: str | None
    scope: dict[str, Any]
    created_at: datetime


class WorkspaceArchived(BaseModel):
    """A workspace was archived (no longer active)"""

    workspace_id: str
    archived_at: datetime
    reason: str


# Delegation Events


class DecisionRightDelegated(BaseModel):
    """
    Authority was delegated from one actor to another

    This creates an edge in the delegation DAG, subject to:
    - TTL constraints (must be <= policy maximum)
    - Acyclic invariant (cannot create cycles)
    """

    delegation_id: str
    workspace_id: str
    from_actor: str
    to_actor: str
    delegated_at: datetime
    ttl_days: int
    expires_at: datetime
    renewable: bool
    visibility: str
    purpose_tag: str | None


class DelegationRenewed(BaseModel):
    """An existing delegation had its TTL extended"""

    delegation_id: str
    renewed_at: datetime
    new_ttl_days: int
    new_expires_at: datetime


class DelegationRevoked(BaseModel):
    """A delegation was explicitly cancelled"""

    delegation_id: str
    revoked_at: datetime
    revoked_by: str
    reason: str | None


class DelegationExpired(BaseModel):
    """A delegation reached its TTL without renewal (system event)"""

    delegation_id: str
    expired_at: datetime


# Law Lifecycle Events


class LawCreated(BaseModel):
    """
    A new law was created in DRAFT status

    Laws start as drafts and must be explicitly activated.
    """

    law_id: str
    workspace_id: str
    title: str
    scope: dict[str, Any]
    reversibility_class: ReversibilityClass
    checkpoints: list[int]
    params: dict[str, Any]
    created_at: datetime
    created_by: str | None


class LawActivated(BaseModel):
    """
    A law moved from DRAFT to ACTIVE

    Activation starts the checkpoint clock and makes the law enforceable.
    """

    law_id: str
    activated_at: datetime
    activated_by: str | None
    next_checkpoint_at: datetime
    next_checkpoint_index: int = 0  # Index into checkpoints list


class LawReviewTriggered(BaseModel):
    """
    A law review was triggered (manual or automatic)

    Reviews are mandatory at checkpoints and can be triggered
    automatically when checkpoints are overdue.
    """

    law_id: str
    triggered_at: datetime
    triggered_by: str | None  # None for system triggers
    reason: str  # "checkpoint_overdue" | "manual" | "performance_threshold"
    checkpoint_index: int | None


class LawReviewCompleted(BaseModel):
    """A law review was completed"""

    law_id: str
    completed_at: datetime
    completed_by: str
    outcome: str  # "continue" | "adjust" | "sunset"
    notes: str | None
    next_checkpoint_at: datetime | None


class LawAdjusted(BaseModel):
    """A law was modified based on review feedback"""

    law_id: str
    adjusted_at: datetime
    adjusted_by: str
    changes: dict[str, Any]  # What changed
    reason: str


class LawSunsetScheduled(BaseModel):
    """A law was scheduled for termination"""

    law_id: str
    scheduled_at: datetime
    sunset_at: datetime
    reason: str


class LawArchived(BaseModel):
    """A law was archived (final state)"""

    law_id: str
    archived_at: datetime
    reason: str


# Feedback Events (Anti-Tyranny Reflexes)


class DelegationConcentrationWarning(BaseModel):
    """
    Warning: Delegation concentration approaching danger threshold

    Emitted automatically when Gini coefficient or in-degree exceeds
    warning thresholds.
    """

    triggered_at: datetime
    gini_coefficient: float
    max_in_degree: int
    warn_threshold_gini: float
    warn_threshold_in_degree: int
    reason: str


class DelegationConcentrationHalt(BaseModel):
    """
    HALT: Delegation concentration exceeded safety threshold

    Emitted automatically when Gini coefficient or in-degree exceeds
    halt thresholds. Triggers automatic safeguards:
    - Transparency escalation
    - New delegation freeze (optional)
    """

    triggered_at: datetime
    gini_coefficient: float
    max_in_degree: int
    halt_threshold_gini: float
    halt_threshold_in_degree: int
    automatic_responses: list[str]  # ["transparency_escalated", etc.]
    reason: str


class TransparencyEscalated(BaseModel):
    """
    System transparency was automatically escalated

    Triggered when HALT conditions are met. Increases visibility
    of aggregate metrics to prevent covert power concentration.
    """

    escalated_at: datetime
    scope: str  # "workspace_id" or "global"
    previous_level: str  # "private", "org_only", "public"
    new_level: str  # "aggregate_only", "aggregate_plus", "full"
    trigger_event: str  # "DelegationConcentrationHalt", etc.
    reason: str


class SystemTick(BaseModel):
    """
    System tick occurred - triggers evaluation loop

    Emitted periodically (e.g., hourly, daily) to evaluate all
    automatic safeguards and health metrics.
    """

    tick_at: datetime
    tick_id: str


# Event type mappings for handlers

LAW_EVENT_TYPES = {
    "WorkspaceCreated": WorkspaceCreated,
    "WorkspaceArchived": WorkspaceArchived,
    "DecisionRightDelegated": DecisionRightDelegated,
    "DelegationRenewed": DelegationRenewed,
    "DelegationRevoked": DelegationRevoked,
    "DelegationExpired": DelegationExpired,
    "LawCreated": LawCreated,
    "LawActivated": LawActivated,
    "LawReviewTriggered": LawReviewTriggered,
    "LawReviewCompleted": LawReviewCompleted,
    "LawAdjusted": LawAdjusted,
    "LawSunsetScheduled": LawSunsetScheduled,
    "LawArchived": LawArchived,
    "DelegationConcentrationWarning": DelegationConcentrationWarning,
    "DelegationConcentrationHalt": DelegationConcentrationHalt,
    "TransparencyEscalated": TransparencyEscalated,
    "SystemTick": SystemTick,
}
