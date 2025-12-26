"""
Law Domain Models - Core entities for governance

These models represent the fundamental building blocks of the governance system.
They use Pydantic for validation and SQLModel for optional ORM capabilities.

Fun fact: A "workspace" is like a jurisdiction - it defines a scope where
certain decisions apply. Think of it as a "governance boundary" rather than
a traditional organizational unit!
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import SQLModel


class ReversibilityClass(str, Enum):
    """
    How difficult it is to undo or modify a law

    This classification directly affects:
    - Required checkpoint frequency
    - Activation barriers
    - Step-size limits (in budget module)

    The more irreversible, the more safeguards apply.
    """

    REVERSIBLE = "REVERSIBLE"  # Easy to change/remove (e.g., meeting schedules)
    SEMI_REVERSIBLE = "SEMI_REVERSIBLE"  # Moderate difficulty (e.g., pilot programs)
    IRREVERSIBLE = "IRREVERSIBLE"  # Hard to undo (e.g., infrastructure, long-term commitments)


class LawStatus(str, Enum):
    """
    Law lifecycle states

    Laws move through these states with mandatory transitions:
    DRAFT → ACTIVE → REVIEW → (ADJUST → ACTIVE) or SUNSET → ARCHIVED
    """

    DRAFT = "DRAFT"  # Being prepared, not yet active
    ACTIVE = "ACTIVE"  # In effect, enforced
    REVIEW = "REVIEW"  # Undergoing mandatory review
    ADJUST = "ADJUST"  # Being modified based on review
    SUNSET = "SUNSET"  # Scheduled for termination
    ARCHIVED = "ARCHIVED"  # No longer active, preserved for record


class Workspace(BaseModel):
    """
    Hierarchical scope of decision authority

    Workspaces define where decisions apply. They can be nested
    (e.g., Country > Region > City > District) creating a tree
    structure for authority delegation and scope containment.

    Attributes:
        workspace_id: Unique identifier
        name: Human-readable name
        parent_workspace_id: Parent in hierarchy (None for root)
        scope: Metadata about territory, time, etc.
        created_at: When workspace was created
        archived_at: When workspace was archived (None if active)
    """

    workspace_id: str
    name: str
    parent_workspace_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    archived_at: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workspace_id": "ws-health-001",
                    "name": "Health Services",
                    "parent_workspace_id": "ws-budapest-001",
                    "scope": {"territory": "Budapest", "domain": "healthcare"},
                    "created_at": "2025-01-15T10:00:00Z",
                    "archived_at": None,
                }
            ]
        }
    }


class Delegation(BaseModel):
    """
    Revocable authority transfer with expiry

    Delegation allows one actor to grant decision rights to another
    within a workspace, subject to:
    - Time-to-live (TTL): Maximum duration before renewal required
    - Revocability: Can be cancelled at any time
    - Scope: Limited to specific workspace

    Attributes:
        delegation_id: Unique identifier
        workspace_id: Where delegation applies
        from_actor: Who is delegating authority
        to_actor: Who receives delegated authority
        delegated_at: When delegation was created
        ttl_days: Days until expiry (must be <= policy maximum)
        expires_at: Computed expiry timestamp
        renewable: Whether delegation can be renewed
        visibility: Who can see this delegation edge
        purpose_tag: Optional label for categorization
        revoked_at: When revoked (None if still active)
    """

    delegation_id: str
    workspace_id: str
    from_actor: str
    to_actor: str
    delegated_at: datetime
    ttl_days: int = Field(ge=1, le=3650)  # 1 day to 10 years
    expires_at: datetime
    renewable: bool = True
    visibility: str = "private"  # "private" | "org_only" | "public"
    purpose_tag: str | None = None
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """Check if delegation is currently active"""
        if self.revoked_at is not None:
            return False
        if now >= self.expires_at:
            return False
        return True

    def days_until_expiry(self, now: datetime) -> int:
        """Get days until expiry (negative if expired)"""
        delta = self.expires_at - now
        return delta.days

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "delegation_id": "del-001",
                    "workspace_id": "ws-health-001",
                    "from_actor": "alice",
                    "to_actor": "dr_bob",
                    "delegated_at": "2025-01-15T10:00:00Z",
                    "ttl_days": 180,
                    "expires_at": "2025-07-14T10:00:00Z",
                    "renewable": True,
                    "visibility": "private",
                    "purpose_tag": "medical_expert",
                    "revoked_at": None,
                }
            ]
        }
    }


class Law(BaseModel):
    """
    Time-bound policy with mandatory review checkpoints

    Laws are not permanent commands - they are hypotheses tested over time.
    Every law has:
    - Explicit scope (where/when it applies)
    - Reversibility classification (how hard to change)
    - Checkpoint schedule (when mandatory reviews occur)
    - Status tracking (lifecycle state)

    Attributes:
        law_id: Unique identifier
        workspace_id: Where law applies
        title: Human-readable title
        scope: Territory, time, population, etc.
        reversibility_class: How difficult to reverse
        checkpoints: Days after activation when reviews are mandatory
        params: Law-specific parameters
        status: Current lifecycle state
        created_at: When law was created
        activated_at: When law became active (None if still in DRAFT)
        next_checkpoint_at: When next review is due
        metadata: Additional tracking information
    """

    law_id: str
    workspace_id: str
    title: str
    scope: dict[str, Any] = Field(default_factory=dict)
    reversibility_class: ReversibilityClass
    checkpoints: list[int] = Field(
        default_factory=list,
        description="Days after activation when reviews are mandatory",
    )
    params: dict[str, Any] = Field(default_factory=dict)
    status: LawStatus = LawStatus.DRAFT
    created_at: datetime
    activated_at: datetime | None = None
    next_checkpoint_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if law is currently active (in effect)"""
        return self.status == LawStatus.ACTIVE

    def is_review_overdue(self, now: datetime) -> bool:
        """Check if review checkpoint is overdue"""
        if self.next_checkpoint_at is None:
            return False
        return now > self.next_checkpoint_at

    def days_until_checkpoint(self, now: datetime) -> int | None:
        """Get days until next checkpoint (None if no checkpoint scheduled)"""
        if self.next_checkpoint_at is None:
            return None
        delta = self.next_checkpoint_at - now
        return delta.days

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "law_id": "law-001",
                    "workspace_id": "ws-health-001",
                    "title": "Primary Care Access Pilot",
                    "scope": {"territory": "District5", "valid_days": 365},
                    "reversibility_class": "SEMI_REVERSIBLE",
                    "checkpoints": [30, 90, 180, 365],
                    "params": {"max_wait_days": 10, "coverage_target": 0.95},
                    "status": "DRAFT",
                    "created_at": "2025-01-15T10:00:00Z",
                    "activated_at": None,
                    "next_checkpoint_at": None,
                    "metadata": {"author": "alice", "version": 1},
                }
            ]
        }
    }


# Projection models (for read-side queries)

class WorkspaceProjection(SQLModel):
    """
    Read model for workspace queries

    This is a denormalized view optimized for fast queries,
    rebuilt from events as needed.
    """

    workspace_id: str
    name: str
    parent_workspace_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    child_count: int = 0
    created_at: datetime


class DelegationEdge(BaseModel):
    """
    Single edge in delegation graph

    Used for building and analyzing the delegation DAG.
    """

    delegation_id: str
    from_actor: str
    to_actor: str
    workspace_id: str
    expires_at: datetime
    is_active: bool


class LawSummary(BaseModel):
    """
    Lightweight law summary for lists/dashboards

    Contains just enough info for overview displays
    without loading full law details.
    """

    law_id: str
    workspace_id: str
    title: str
    status: LawStatus
    reversibility_class: ReversibilityClass
    next_checkpoint_at: datetime | None
    is_review_overdue: bool
