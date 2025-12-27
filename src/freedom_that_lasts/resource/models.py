"""
Resource & Procurement Domain Models

Evidence-based capability claims, binary requirement matching, and tender lifecycle models.

Fun fact: The concept of "verifiable credentials" dates back to medieval guild systems
where craftsmen needed documented proof of their skills from master artisans -
we're just adding cryptographic verification and expiration dates!
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TenderStatus(str, Enum):
    """
    Tender lifecycle states

    Finite state machine:
    DRAFT → OPEN → EVALUATING → AWARDED → IN_DELIVERY → COMPLETED
                                     ↓
                                CANCELLED (terminal state from any state)
    """

    DRAFT = "DRAFT"  # Being prepared
    OPEN = "OPEN"  # Accepting submissions
    EVALUATING = "EVALUATING"  # Computing feasible set
    AWARDED = "AWARDED"  # Winner selected
    IN_DELIVERY = "IN_DELIVERY"  # Work in progress
    COMPLETED = "COMPLETED"  # Successfully delivered
    CANCELLED = "CANCELLED"  # Cancelled before completion


class SelectionMethod(str, Enum):
    """
    Constitutional supplier selection mechanisms (no discretion)

    ROTATION: Load balancing across suppliers (anti-monopolization)
    RANDOM: Auditable random selection (seed-based, verifiable)
    ROTATION_WITH_RANDOM: Hybrid - rotate among low-loaded suppliers, then random
    """

    ROTATION = "ROTATION"
    RANDOM = "RANDOM"
    ROTATION_WITH_RANDOM = "ROTATION_WITH_RANDOM"


class Evidence(BaseModel):
    """
    Verifiable evidence for capability claims

    Every capability claim MUST have evidence. No evidence = no claim.
    Evidence can expire, invalidating the capability claim.

    Fun fact: The ancient Romans required two witnesses for any legal contract -
    we require cryptographically verifiable evidence with expiration tracking!
    """

    evidence_id: str = Field(..., description="Unique evidence identifier")
    evidence_type: str = Field(
        ...,
        description="Type of evidence: certification, audit_report, reference, measurement, test_result",
    )
    issuer: str = Field(
        ...,
        description="Who verified: authority, auditor, automated system, customer",
    )
    issued_at: datetime = Field(..., description="When evidence was issued")
    valid_until: datetime | None = Field(
        default=None, description="Expiration date (None = no expiry)"
    )
    document_uri: str | None = Field(
        default=None, description="Link to document or hash"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )

    @field_validator("evidence_type")
    @classmethod
    def validate_evidence_type(cls, v: str) -> str:
        """Validate evidence type is non-empty"""
        if not v or not v.strip():
            raise ValueError("Evidence type cannot be empty")
        return v.strip()

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, v: str) -> str:
        """Validate issuer is non-empty"""
        if not v or not v.strip():
            raise ValueError("Evidence issuer cannot be empty")
        return v.strip()

    def is_expired(self, check_time: datetime) -> bool:
        """Check if evidence has expired"""
        if self.valid_until is None:
            return False
        return check_time > self.valid_until


class CapabilityClaim(BaseModel):
    """
    Binary capability claim with verifiable evidence

    Claims are YES/NO (not scored or ranked). Either you have the capability or you don't.
    Every claim requires evidence - no self-certification without proof.

    Fun fact: Medieval guild systems had three capability levels: apprentice, journeyman, master.
    We keep it simpler - you either meet the capability requirement or you don't!
    """

    claim_id: str = Field(..., description="Unique claim identifier")
    supplier_id: str = Field(..., description="Supplier making the claim")
    capability_type: str = Field(
        ...,
        description="Capability type: ISO27001, 50_welders, 24_7_support, EU_procurement_compliant, etc.",
    )
    scope: dict[str, Any] = Field(
        ...,
        description="Territory, time range, quantity limits (structured constraints)",
    )
    valid_from: datetime = Field(..., description="Claim validity start date")
    valid_until: datetime | None = Field(
        default=None, description="Claim expiration (None = no expiry)"
    )
    evidence: list[Evidence] = Field(
        ..., min_length=1, description="Required evidence (at least one)"
    )
    verified: bool = Field(
        default=False, description="Has evidence been validated by system?"
    )
    capacity: dict[str, Any] | None = Field(
        default=None,
        description="Throughput, ramp_up_time, constraints (first-class capacity data)",
    )

    @field_validator("capability_type")
    @classmethod
    def validate_capability_type(cls, v: str) -> str:
        """Validate capability type is non-empty"""
        if not v or not v.strip():
            raise ValueError("Capability type cannot be empty")
        return v.strip()

    @field_validator("evidence")
    @classmethod
    def validate_evidence_required(cls, v: list[Evidence]) -> list[Evidence]:
        """Validate at least one evidence item exists"""
        if not v or len(v) == 0:
            raise ValueError(
                "At least one evidence item required - no claim without proof"
            )
        return v

    def is_valid_at(self, check_time: datetime) -> bool:
        """Check if claim is valid at given time"""
        if check_time < self.valid_from:
            return False
        if self.valid_until is not None and check_time > self.valid_until:
            return False
        return True

    def has_expired_evidence(self, check_time: datetime) -> bool:
        """Check if any evidence has expired"""
        return any(e.is_expired(check_time) for e in self.evidence)


class Supplier(BaseModel):
    """
    Supplier aggregate with evidence-based capabilities

    Reputation is threshold-based (pass/fail), not ranking.
    Total value awarded tracks concentration for anti-capture monitoring.

    Fun fact: The first procurement regulations were established in ancient China
    during the Qin Dynasty (221-206 BC) to prevent corruption in public works!
    """

    supplier_id: str = Field(..., description="Unique supplier identifier")
    name: str = Field(..., description="Supplier name")
    supplier_type: str = Field(
        ...,
        description="Type: company, public_agency, individual, cooperative, consortium",
    )
    capabilities: dict[str, CapabilityClaim] = Field(
        default_factory=dict, description="Capability type → claim mapping"
    )
    reputation_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Delivery performance score (0.0-1.0, default 0.5 for new suppliers)",
    )
    total_value_awarded: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Cumulative contract value (for concentration metrics)",
    )
    created_at: datetime = Field(..., description="Registration timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional supplier information"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name is non-empty"""
        if not v or not v.strip():
            raise ValueError("Supplier name cannot be empty")
        return v.strip()

    @field_validator("supplier_type")
    @classmethod
    def validate_supplier_type(cls, v: str) -> str:
        """Validate supplier type is non-empty"""
        if not v or not v.strip():
            raise ValueError("Supplier type cannot be empty")
        return v.strip()

    def has_capability(
        self, capability_type: str, check_time: datetime
    ) -> tuple[bool, str | None]:
        """
        Check if supplier has valid capability at given time

        Returns: (has_capability, reason_if_not)
        """
        if capability_type not in self.capabilities:
            return False, f"Capability '{capability_type}' not claimed"

        claim = self.capabilities[capability_type]

        if not claim.is_valid_at(check_time):
            return False, f"Capability '{capability_type}' claim expired or not yet valid"

        if claim.has_expired_evidence(check_time):
            return (
                False,
                f"Capability '{capability_type}' has expired evidence",
            )

        if not claim.verified:
            return False, f"Capability '{capability_type}' evidence not yet verified"

        return True, None


class TenderRequirement(BaseModel):
    """
    Binary tender requirement (supplier meets it or doesn't)

    No scoring, no weighting - just yes/no matching.
    """

    requirement_id: str = Field(..., description="Unique requirement identifier")
    capability_type: str = Field(
        ..., description="Required capability (must match CapabilityClaim.capability_type)"
    )
    min_capacity: dict[str, Any] | None = Field(
        default=None, description="Minimum capacity requirements (throughput, etc.)"
    )
    mandatory: bool = Field(
        default=True, description="Is this requirement mandatory? (default: true)"
    )

    @field_validator("capability_type")
    @classmethod
    def validate_capability_type(cls, v: str) -> str:
        """Validate capability type is non-empty"""
        if not v or not v.strip():
            raise ValueError("Capability type cannot be empty")
        return v.strip()


class Tender(BaseModel):
    """
    Tender aggregate for law-mandated procurement

    Linked to law (execution requirement) and optionally to budget.
    Feasible set computed via binary requirement matching (no scoring).
    Selection via constitutional mechanism (rotation/random/hybrid).

    Fun fact: The first recorded competitive tender was in 1782 when the British Navy
    sought bids for biscuits (ship provisions). We've added evidence requirements
    and cryptographic randomness since then!
    """

    tender_id: str = Field(..., description="Unique tender identifier")
    law_id: str = Field(..., description="Linked law (execution requirement)")
    budget_item_id: str | None = Field(
        default=None, description="Optional budget item link"
    )
    title: str = Field(..., description="Tender title")
    description: str = Field(..., description="Tender description")
    requirements: list[TenderRequirement] = Field(
        ..., min_length=1, description="Binary requirements (at least one)"
    )
    required_capacity: dict[str, Any] | None = Field(
        default=None, description="Overall capacity needs (throughput, timeline, etc.)"
    )
    sla_requirements: dict[str, Any] | None = Field(
        default=None, description="Quality gates and SLA thresholds"
    )
    evidence_required: list[str] = Field(
        default_factory=list, description="Required evidence types from suppliers"
    )
    acceptance_tests: list[dict[str, Any]] = Field(
        default_factory=list, description="Deliverable verification tests"
    )
    estimated_value: Decimal | None = Field(
        default=None, ge=0, description="Estimated contract value"
    )
    status: TenderStatus = Field(
        default=TenderStatus.DRAFT, description="Current tender status"
    )
    feasible_suppliers: list[str] = Field(
        default_factory=list, description="Computed feasible supplier IDs"
    )
    selected_supplier_id: str | None = Field(
        default=None, description="Selected supplier ID (after selection)"
    )
    selection_method: SelectionMethod = Field(
        default=SelectionMethod.ROTATION_WITH_RANDOM,
        description="Constitutional selection mechanism",
    )
    selection_reason: str | None = Field(
        default=None, description="Audit trail for selection decision"
    )
    created_at: datetime = Field(..., description="Tender creation timestamp")
    opened_at: datetime | None = Field(default=None, description="When tender opened")
    closed_at: datetime | None = Field(default=None, description="When tender closed")
    awarded_at: datetime | None = Field(
        default=None, description="When tender awarded"
    )
    completed_at: datetime | None = Field(
        default=None, description="When delivery completed"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is non-empty"""
        if not v or not v.strip():
            raise ValueError("Tender title cannot be empty")
        return v.strip()

    @field_validator("requirements")
    @classmethod
    def validate_requirements_not_empty(
        cls, v: list[TenderRequirement]
    ) -> list[TenderRequirement]:
        """Validate at least one requirement exists"""
        if not v or len(v) == 0:
            raise ValueError("At least one requirement required for tender")
        return v
