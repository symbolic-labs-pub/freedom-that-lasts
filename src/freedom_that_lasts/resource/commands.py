"""
Resource & Procurement Commands

Commands express intentions to modify supplier/tender state.
All validation happens in handlers via invariants (defense in depth).

Fun fact: The command pattern was formalized by the Gang of Four in 1994,
but Julius Caesar used written commands (sealed tablets) to manage his legions
in 50 BC - proving that good design patterns transcend technology!
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.resource.models import SelectionMethod


# ============================================================================
# Supplier & Capability Management Commands
# ============================================================================


class RegisterSupplier(BaseModel):
    """
    Register new supplier in capability registry

    Creates supplier with initial reputation score of 0.5 (neutral).
    Capabilities added separately via AddCapabilityClaim.
    """

    name: str = Field(..., description="Supplier name")
    supplier_type: str = Field(
        ...,
        description="Type: company, public_agency, individual, cooperative, consortium",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional supplier information"
    )


class EvidenceSpec(BaseModel):
    """Evidence specification for capability claims"""

    evidence_type: str = Field(..., description="certification, audit_report, reference, measurement")
    issuer: str = Field(..., description="Who verified the evidence")
    issued_at: datetime | str = Field(..., description="When evidence was issued")
    valid_until: datetime | str | None = Field(
        default=None, description="Expiration date (None = no expiry)"
    )
    document_uri: str | None = Field(
        default=None, description="Link to document or hash"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class AddCapabilityClaim(BaseModel):
    """
    Add capability claim to supplier with verifiable evidence

    Every claim requires evidence - no self-certification without proof.
    Claims are binary (yes/no), not scored or ranked.
    """

    supplier_id: str = Field(..., description="Supplier making the claim")
    capability_type: str = Field(
        ...,
        description="Capability type: ISO27001, 50_welders, 24_7_support, etc.",
    )
    scope: dict[str, Any] = Field(
        ...,
        description="Territory, time range, quantity limits (structured constraints)",
    )
    valid_from: datetime | str = Field(..., description="Claim validity start date")
    valid_until: datetime | str | None = Field(
        default=None, description="Claim expiration (None = no expiry)"
    )
    evidence: list[EvidenceSpec] = Field(
        ..., min_length=1, description="Required evidence (at least one)"
    )
    capacity: dict[str, Any] | None = Field(
        default=None,
        description="Throughput, ramp_up_time, constraints (first-class capacity data)",
    )


class UpdateCapabilityClaim(BaseModel):
    """
    Update existing capability claim (evidence, validity, capacity)

    Allows extending validity, adding evidence, or updating capacity.
    Cannot change capability_type (requires revoke + re-add).
    """

    claim_id: str = Field(..., description="Claim to update")
    evidence: list[EvidenceSpec] | None = Field(
        default=None, description="Add or update evidence"
    )
    valid_until: datetime | str | None = Field(
        default=None, description="Extend or change validity"
    )
    capacity: dict[str, Any] | None = Field(
        default=None, description="Update capacity information"
    )


class RevokeCapabilityClaim(BaseModel):
    """
    Revoke capability claim (evidence invalidated or capability lost)

    Prevents supplier from being selected for tenders requiring this capability.
    """

    claim_id: str = Field(..., description="Claim to revoke")
    reason: str = Field(..., description="Reason for revocation")


# ============================================================================
# Tender Lifecycle Commands
# ============================================================================


class RequirementSpec(BaseModel):
    """Tender requirement specification"""

    capability_type: str = Field(
        ..., description="Required capability (matches CapabilityClaim.capability_type)"
    )
    min_capacity: dict[str, Any] | None = Field(
        default=None, description="Minimum capacity requirements"
    )
    mandatory: bool = Field(default=True, description="Is requirement mandatory?")


class CreateTender(BaseModel):
    """
    Create tender for law-mandated procurement

    Tender starts in DRAFT status. Requirements define feasible set via binary matching.
    Law must be ACTIVE. Budget item optional but recommended.

    Fun fact: The word 'tender' comes from the Latin 'tendere' meaning 'to stretch out' -
    as in stretching out an offer. We're stretching procurement beyond capture resistance!
    """

    law_id: str = Field(..., description="Linked law (execution requirement)")
    title: str = Field(..., description="Tender title")
    description: str = Field(..., description="Tender description")
    requirements: list[RequirementSpec] = Field(
        ..., min_length=1, description="Binary requirements (at least one)"
    )
    required_capacity: dict[str, Any] | None = Field(
        default=None, description="Overall capacity needs"
    )
    sla_requirements: dict[str, Any] | None = Field(
        default=None, description="Quality gates and SLA thresholds"
    )
    evidence_required: list[str] = Field(
        default_factory=list, description="Required evidence types"
    )
    acceptance_tests: list[dict[str, Any]] = Field(
        default_factory=list, description="Deliverable verification tests"
    )
    estimated_value: Decimal | None = Field(
        default=None, description="Estimated contract value"
    )
    budget_item_id: str | None = Field(
        default=None, description="Optional budget item link"
    )
    selection_method: SelectionMethod = Field(
        default=SelectionMethod.ROTATION_WITH_RANDOM,
        description="Constitutional selection mechanism",
    )


class OpenTender(BaseModel):
    """
    Open tender for submissions (DRAFT → OPEN transition)

    Makes tender visible to suppliers and starts submission period.
    """

    tender_id: str = Field(..., description="Tender to open")


class EvaluateTender(BaseModel):
    """
    Evaluate tender - compute feasible set via binary requirement matching

    No scoring, no weighting - suppliers either meet ALL requirements or don't.
    Feasible set = { supplier | ∀ requirement: supplier.has_capability(requirement) }

    Evaluation is deterministic and auditable.
    """

    tender_id: str = Field(..., description="Tender to evaluate")
    evaluation_time: datetime | str | None = Field(
        default=None, description="Evaluation timestamp (for deterministic testing)"
    )


class SelectSupplier(BaseModel):
    """
    Select supplier from feasible set using constitutional mechanism

    Multi-gate enforcement:
    1. Feasible set must be non-empty
    2. Selection method must match tender configuration
    3. Supplier share limits enforced (anti-capture)
    4. Reputation threshold applied (if configured)

    No discretion - selection is algorithmic and auditable.
    """

    tender_id: str = Field(..., description="Tender for selection")
    selection_seed: str | None = Field(
        default=None, description="Seed for auditable randomness (required if RANDOM method)"
    )


class AwardTender(BaseModel):
    """
    Award tender to selected supplier with contract terms

    Formalizes contract value and terms. Updates supplier's total_value_awarded
    for concentration monitoring.
    """

    tender_id: str = Field(..., description="Tender to award")
    contract_value: Decimal = Field(..., ge=0, description="Final contract value")
    contract_terms: dict[str, Any] = Field(
        ..., description="Contract terms, payment schedule, penalties, etc."
    )


class CancelTender(BaseModel):
    """
    Cancel tender before completion

    Can cancel from any state. Records reason for audit trail.
    """

    tender_id: str = Field(..., description="Tender to cancel")
    reason: str = Field(..., description="Cancellation reason")


# ============================================================================
# Delivery Tracking Commands
# ============================================================================


class RecordMilestone(BaseModel):
    """
    Record delivery milestone with evidence

    Tracks progress through tender execution. Critical milestones should include evidence.
    Feeds into supplier reputation calculation.
    """

    tender_id: str = Field(..., description="Tender for milestone")
    milestone_id: str = Field(..., description="Milestone identifier")
    milestone_type: str = Field(
        ...,
        description="Type: started, progress, completed, test_passed, test_failed, delayed",
    )
    description: str = Field(..., description="Milestone description")
    evidence: list[EvidenceSpec] = Field(
        default_factory=list, description="Supporting evidence (optional but recommended)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional milestone context"
    )


class RecordSLABreach(BaseModel):
    """
    Record SLA breach during delivery

    Tracks quality issues and impacts supplier reputation.
    Severe breaches trigger automatic notifications.
    """

    tender_id: str = Field(..., description="Tender with SLA breach")
    sla_metric: str = Field(..., description="Breached SLA metric")
    expected_value: Any = Field(..., description="Expected SLA value")
    actual_value: Any = Field(..., description="Actual value")
    severity: str = Field(
        ..., description="Severity: minor, major, critical"
    )
    impact_description: str = Field(..., description="Impact of breach")


class CompleteTender(BaseModel):
    """
    Complete tender with quality assessment

    Updates supplier reputation based on delivery quality.
    Quality score feeds into reputation threshold enforcement.

    Fun fact: Modern supplier rating systems originated from medieval guild quality marks -
    but we've replaced subjective 'stars' with objective performance metrics!
    """

    tender_id: str = Field(..., description="Tender to complete")
    completion_report: dict[str, Any] = Field(
        ..., description="Completion details, tests passed, delivery metrics"
    )
    final_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Quality score (0.0-1.0) for reputation update"
    )
