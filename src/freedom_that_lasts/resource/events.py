"""
Resource & Procurement Events

Events are immutable facts about what happened.
They form the source of truth for all resource/procurement state.

Fun fact: The concept of event sourcing mirrors how historians work - they reconstruct
history from primary sources (events), not by trusting summary documents that could be forged!
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from freedom_that_lasts.resource.models import SelectionMethod


# ============================================================================
# Supplier & Capability Events
# ============================================================================


class SupplierRegistered(BaseModel):
    """Supplier registered in capability registry"""

    supplier_id: str = Field(..., description="Unique supplier identifier")
    name: str = Field(..., description="Supplier name")
    supplier_type: str = Field(..., description="Type: company, public_agency, etc.")
    registered_at: datetime = Field(..., description="Registration timestamp")
    registered_by: str = Field(..., description="Actor who registered supplier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional supplier information"
    )


class CapabilityClaimAdded(BaseModel):
    """Capability claim added to supplier with evidence"""

    claim_id: str = Field(..., description="Unique claim identifier")
    supplier_id: str = Field(..., description="Supplier making the claim")
    capability_type: str = Field(..., description="Capability type")
    scope: dict[str, Any] = Field(..., description="Capability scope constraints")
    valid_from: datetime = Field(..., description="Claim validity start")
    valid_until: datetime | None = Field(default=None, description="Claim expiration")
    evidence: list[dict[str, Any]] = Field(
        ..., description="Evidence items (serialized)"
    )
    capacity: dict[str, Any] | None = Field(
        default=None, description="Capacity information"
    )
    added_at: datetime = Field(..., description="When claim was added")
    added_by: str = Field(..., description="Actor who added claim")


class CapabilityClaimUpdated(BaseModel):
    """Capability claim updated (evidence, validity, capacity)"""

    claim_id: str = Field(..., description="Claim identifier")
    supplier_id: str = Field(..., description="Supplier ID")
    updated_evidence: list[dict[str, Any]] | None = Field(
        default=None, description="New or updated evidence"
    )
    updated_validity: datetime | None = Field(
        default=None, description="Extended validity"
    )
    updated_capacity: dict[str, Any] | None = Field(
        default=None, description="Updated capacity"
    )
    updated_at: datetime = Field(..., description="Update timestamp")
    updated_by: str = Field(..., description="Actor who updated claim")


class CapabilityClaimRevoked(BaseModel):
    """Capability claim revoked (evidence invalid or capability lost)"""

    claim_id: str = Field(..., description="Revoked claim identifier")
    supplier_id: str = Field(..., description="Supplier ID")
    capability_type: str = Field(..., description="Capability type")
    revoked_at: datetime = Field(..., description="Revocation timestamp")
    reason: str = Field(..., description="Reason for revocation")
    revoked_by: str = Field(..., description="Actor who revoked claim")


# ============================================================================
# Tender Lifecycle Events
# ============================================================================


class TenderCreated(BaseModel):
    """Tender created for law-mandated procurement"""

    tender_id: str = Field(..., description="Unique tender identifier")
    law_id: str = Field(..., description="Linked law")
    title: str = Field(..., description="Tender title")
    description: str = Field(..., description="Tender description")
    requirements: list[dict[str, Any]] = Field(
        ..., description="Requirements (serialized)"
    )
    required_capacity: dict[str, Any] | None = Field(
        default=None, description="Required capacity"
    )
    sla_requirements: dict[str, Any] | None = Field(
        default=None, description="SLA requirements"
    )
    evidence_required: list[str] = Field(
        default_factory=list, description="Required evidence types"
    )
    acceptance_tests: list[dict[str, Any]] = Field(
        default_factory=list, description="Acceptance tests"
    )
    estimated_value: Decimal | None = Field(
        default=None, description="Estimated value"
    )
    budget_item_id: str | None = Field(default=None, description="Budget link")
    selection_method: SelectionMethod = Field(
        ..., description="Selection mechanism"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: str = Field(..., description="Creator actor")


class TenderOpened(BaseModel):
    """Tender opened for submissions (DRAFT → OPEN)"""

    tender_id: str = Field(..., description="Tender identifier")
    opened_at: datetime = Field(..., description="Open timestamp")
    opened_by: str = Field(..., description="Actor who opened tender")


class FeasibleSetComputed(BaseModel):
    """
    Feasible set computed via binary requirement matching

    Documents deterministic evaluation of which suppliers meet ALL requirements.
    Excluded suppliers tracked with reasons for transparency.
    """

    tender_id: str = Field(..., description="Tender identifier")
    evaluation_time: datetime = Field(..., description="Evaluation timestamp")
    total_suppliers_evaluated: int = Field(
        ..., description="Total suppliers in registry"
    )
    feasible_suppliers: list[str] = Field(
        ..., description="Supplier IDs that meet ALL requirements"
    )
    excluded_suppliers_with_reasons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Excluded suppliers with reasons: [{supplier_id, reasons[]}]",
    )
    computation_method: str = Field(
        default="binary_requirement_matching",
        description="Algorithm used for feasible set computation",
    )
    computed_by: str = Field(..., description="System or actor")


class SupplierSelected(BaseModel):
    """
    Supplier selected from feasible set via constitutional mechanism

    Records selection method, reason (rotation index or random seed), and full
    state for auditability. No discretion - selection is algorithmic.

    Fun fact: The ancient Athenian democracy used a randomization device called a
    'kleroterion' (lottery machine) to select officials - we use cryptographic seeds!
    """

    tender_id: str = Field(..., description="Tender identifier")
    selected_supplier_id: str = Field(..., description="Selected supplier")
    selection_method: SelectionMethod = Field(..., description="Method used")
    selection_reason: str = Field(
        ..., description="Audit trail: rotation index, random seed, etc."
    )
    rotation_state: dict[str, Any] | None = Field(
        default=None, description="Supplier load state at selection time"
    )
    random_seed: str | None = Field(
        default=None, description="Random seed (if applicable)"
    )
    selected_at: datetime = Field(..., description="Selection timestamp")
    selected_by: str = Field(..., description="System or actor")


class SupplierSelectionFailed(BaseModel):
    """Supplier selection failed (empty feasible set or other issue)"""

    tender_id: str = Field(..., description="Tender identifier")
    failure_reason: str = Field(..., description="Why selection failed")
    empty_feasible_set: bool = Field(
        ..., description="Was feasible set empty?"
    )
    attempted_at: datetime = Field(..., description="Attempt timestamp")
    attempted_by: str = Field(..., description="System or actor")


class TenderAwarded(BaseModel):
    """Tender awarded to selected supplier with contract terms"""

    tender_id: str = Field(..., description="Tender identifier")
    awarded_supplier_id: str = Field(..., description="Awarded supplier")
    contract_value: Decimal = Field(..., description="Final contract value")
    contract_terms: dict[str, Any] = Field(..., description="Contract terms")
    awarded_at: datetime = Field(..., description="Award timestamp")
    awarded_by: str = Field(..., description="Actor who awarded")


class TenderCancelled(BaseModel):
    """Tender cancelled before completion"""

    tender_id: str = Field(..., description="Tender identifier")
    cancelled_at: datetime = Field(..., description="Cancellation timestamp")
    reason: str = Field(..., description="Cancellation reason")
    cancelled_by: str = Field(..., description="Actor who cancelled")


# ============================================================================
# Delivery Tracking Events
# ============================================================================


class MilestoneRecorded(BaseModel):
    """Delivery milestone recorded with evidence"""

    tender_id: str = Field(..., description="Tender identifier")
    milestone_id: str = Field(..., description="Milestone identifier")
    milestone_type: str = Field(..., description="Milestone type")
    description: str = Field(..., description="Milestone description")
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="Supporting evidence"
    )
    recorded_at: datetime = Field(..., description="Recording timestamp")
    recorded_by: str = Field(..., description="Actor who recorded")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class SLABreachDetected(BaseModel):
    """SLA breach detected during delivery"""

    tender_id: str = Field(..., description="Tender identifier")
    sla_metric: str = Field(..., description="Breached metric")
    expected_value: Any = Field(..., description="Expected value")
    actual_value: Any = Field(..., description="Actual value")
    severity: str = Field(..., description="Severity: minor, major, critical")
    impact_description: str = Field(..., description="Impact of breach")
    detected_at: datetime = Field(..., description="Detection timestamp")


class TenderCompleted(BaseModel):
    """Tender completed with quality assessment"""

    tender_id: str = Field(..., description="Tender identifier")
    completed_at: datetime = Field(..., description="Completion timestamp")
    completion_report: dict[str, Any] = Field(
        ..., description="Completion details and metrics"
    )
    final_quality_score: float = Field(
        ..., description="Quality score (0.0-1.0)"
    )
    completed_by: str = Field(..., description="Actor who completed")


class ReputationUpdated(BaseModel):
    """
    Supplier reputation updated based on delivery performance

    Reputation is threshold-based (pass/fail), not ranking.
    Used for minimum reputation gate in supplier selection.
    """

    supplier_id: str = Field(..., description="Supplier identifier")
    old_score: float = Field(..., description="Previous reputation score")
    new_score: float = Field(..., description="New reputation score")
    reason: str = Field(..., description="Reason for update")
    tender_id: str | None = Field(
        default=None, description="Linked tender (if applicable)"
    )
    updated_at: datetime = Field(..., description="Update timestamp")


# ============================================================================
# Trigger Events (System Reflexes)
# ============================================================================


class EmptyFeasibleSetDetected(BaseModel):
    """
    Empty feasible set detected - no suppliers meet requirements

    Trigger event: Indicates requirements too strict or supplier base insufficient.
    Should trigger law review to adjust requirements or build supplier capacity.

    Fun fact: The first recorded 'failed tender' was in 1840 when the British government
    sought bids for a new prison design - all submissions rejected as too expensive!
    """

    tender_id: str = Field(..., description="Tender with empty feasible set")
    law_id: str = Field(..., description="Linked law")
    detected_at: datetime = Field(..., description="Detection timestamp")
    requirements_summary: dict[str, Any] = Field(
        ..., description="Requirements that couldn't be met"
    )
    action_required: str = Field(
        default="Review requirements or build supplier capacity",
        description="Recommended action",
    )


class SupplierConcentrationWarning(BaseModel):
    """
    Supplier concentration warning - single supplier approaching limit

    Trigger event: Warning threshold exceeded (default 20%).
    System should diversify procurement to prevent capture.
    """

    detected_at: datetime = Field(..., description="Detection timestamp")
    total_procurement_value: Decimal = Field(
        ..., description="Total contract value across all suppliers"
    )
    supplier_shares: dict[str, float] = Field(
        ..., description="supplier_id → share percentage (0.0-1.0)"
    )
    gini_coefficient: float = Field(
        ..., description="Gini coefficient of supplier concentration"
    )
    top_supplier_id: str = Field(..., description="Supplier with highest share")
    top_supplier_share: float = Field(..., description="Share of top supplier")
    threshold_exceeded: float = Field(
        ..., description="Warning threshold that was exceeded"
    )


class SupplierConcentrationHalt(BaseModel):
    """
    Supplier concentration halt - single supplier exceeded critical limit

    Trigger event: Halt threshold exceeded (default 35%).
    Supplier excluded from rotation until diversification achieved.
    """

    detected_at: datetime = Field(..., description="Detection timestamp")
    total_procurement_value: Decimal = Field(
        ..., description="Total contract value"
    )
    supplier_shares: dict[str, float] = Field(
        ..., description="supplier_id → share percentage"
    )
    gini_coefficient: float = Field(..., description="Gini coefficient")
    halted_supplier_id: str = Field(
        ..., description="Supplier excluded from rotation"
    )
    supplier_share: float = Field(..., description="Share that triggered halt")
    critical_threshold_exceeded: float = Field(
        ..., description="Critical threshold exceeded"
    )
