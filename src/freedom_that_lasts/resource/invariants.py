"""
Resource & Procurement Invariants

Pure validation functions that enforce business rules.
All validation logic centralized here for testability and defense in depth.

Fun fact: The term 'invariant' comes from mathematical logic - properties that must
always remain true throughout a computation. Like democracy requiring periodic elections,
procurement requires evidence for every capability claim!
"""

from datetime import datetime
from typing import Any

from freedom_that_lasts.resource.models import Evidence, SelectionMethod


# ============================================================================
# Custom Exceptions
# ============================================================================


class ResourceInvariantError(Exception):
    """Base exception for resource invariant violations"""

    pass


class EvidenceRequiredError(ResourceInvariantError):
    """Evidence is required but not provided"""

    pass


class EvidenceExpiredError(ResourceInvariantError):
    """Evidence has expired"""

    pass


class CapabilityClaimNotUniqueError(ResourceInvariantError):
    """Supplier already has claim for this capability type"""

    pass


class InvalidTenderRequirementError(ResourceInvariantError):
    """Tender requirement is invalid"""

    pass


class LawNotActiveForProcurementError(ResourceInvariantError):
    """Law must be ACTIVE to start procurement"""

    pass


class FeasibleSetEmptyError(ResourceInvariantError):
    """Feasible set is empty - no suppliers meet requirements"""

    pass


class InvalidSelectionMethodError(ResourceInvariantError):
    """Selection method does not match tender configuration"""

    pass


class SupplierNotInFeasibleSetError(ResourceInvariantError):
    """Selected supplier is not in feasible set"""

    pass


class SupplierShareExceededError(ResourceInvariantError):
    """Supplier share exceeds concentration limit"""

    pass


class RandomSeedRequiredError(ResourceInvariantError):
    """Random seed required for auditable randomness"""

    pass


class MilestoneEvidenceRequiredError(ResourceInvariantError):
    """Critical milestone requires evidence"""

    pass


class InvalidQualityScoreError(ResourceInvariantError):
    """Quality score must be between 0.0 and 1.0"""

    pass


class InvalidReputationScoreError(ResourceInvariantError):
    """Reputation score must be between 0.0 and 1.0"""

    pass


# ============================================================================
# Evidence & Capability Validation
# ============================================================================


def validate_evidence_required(evidence: list[Evidence] | None) -> None:
    """
    Validate that at least one evidence item is provided

    No capability claim without proof - structural anti-fraud measure.

    Raises:
        EvidenceRequiredError: If no evidence provided
    """
    if evidence is None or len(evidence) == 0:
        raise EvidenceRequiredError(
            "At least one evidence item required - no claim without proof"
        )


def validate_evidence_not_expired(evidence: Evidence, check_time: datetime) -> None:
    """
    Validate that evidence has not expired at check time

    Expired evidence invalidates capability claims.

    Args:
        evidence: Evidence to check
        check_time: Time to check expiration against

    Raises:
        EvidenceExpiredError: If evidence expired
    """
    if evidence.valid_until is not None and check_time > evidence.valid_until:
        raise EvidenceExpiredError(
            f"Evidence {evidence.evidence_id} expired on {evidence.valid_until}"
        )


def validate_capability_claim_unique(
    existing_capabilities: dict[str, Any], capability_type: str
) -> None:
    """
    Validate that supplier doesn't already have claim for this capability type

    Prevents duplicate claims polluting registry.

    Args:
        existing_capabilities: Supplier's current capabilities
        capability_type: New capability type to add

    Raises:
        CapabilityClaimNotUniqueError: If duplicate capability type
    """
    if capability_type in existing_capabilities:
        raise CapabilityClaimNotUniqueError(
            f"Supplier already has capability claim for '{capability_type}'"
        )


# ============================================================================
# Tender Requirement Validation
# ============================================================================


def validate_tender_requirements(requirements: list[dict[str, Any]]) -> None:
    """
    Validate tender requirements are well-formed

    Requirements must:
    - Have at least one requirement
    - Each requirement must have capability_type
    - capability_type must be non-empty

    Args:
        requirements: List of requirement dictionaries

    Raises:
        InvalidTenderRequirementError: If requirements invalid
    """
    if not requirements or len(requirements) == 0:
        raise InvalidTenderRequirementError(
            "At least one requirement required for tender"
        )

    for req in requirements:
        if "capability_type" not in req:
            raise InvalidTenderRequirementError(
                f"Requirement {req.get('requirement_id', 'unknown')} missing capability_type"
            )

        capability_type = req["capability_type"]
        if not capability_type or not str(capability_type).strip():
            raise InvalidTenderRequirementError(
                f"Requirement {req.get('requirement_id', 'unknown')} has empty capability_type"
            )


# ============================================================================
# Feasible Set Validation
# ============================================================================


def validate_feasible_set_not_empty(feasible_suppliers: list[str] | None) -> None:
    """
    Validate feasible set is not empty

    Empty feasible set indicates requirements too strict or supplier base insufficient.
    Should trigger law review.

    Args:
        feasible_suppliers: List of feasible supplier IDs

    Raises:
        FeasibleSetEmptyError: If feasible set is empty
    """
    if feasible_suppliers is None or len(feasible_suppliers) == 0:
        raise FeasibleSetEmptyError(
            "No suppliers meet all requirements - feasible set is empty. "
            "Consider reviewing requirements or building supplier capacity."
        )


# ============================================================================
# Selection Validation
# ============================================================================


def validate_selection_method(
    actual_method: SelectionMethod, expected_method: SelectionMethod
) -> None:
    """
    Validate selection method matches tender configuration

    Cannot change selection method after tender created (constitutional rule).

    Args:
        actual_method: Selection method being used
        expected_method: Selection method configured in tender

    Raises:
        InvalidSelectionMethodError: If methods don't match
    """
    if actual_method != expected_method:
        raise InvalidSelectionMethodError(
            f"Selection method {actual_method.value} does not match "
            f"tender configuration {expected_method.value}"
        )


def validate_supplier_in_feasible_set(
    supplier_id: str, feasible_suppliers: list[str]
) -> None:
    """
    Validate supplier is in feasible set

    Cannot select supplier outside feasible set (no manual override).

    Args:
        supplier_id: Supplier to validate
        feasible_suppliers: List of feasible supplier IDs

    Raises:
        SupplierNotInFeasibleSetError: If supplier not in set
    """
    if supplier_id not in feasible_suppliers:
        raise SupplierNotInFeasibleSetError(
            f"Supplier {supplier_id} is not in feasible set - cannot select"
        )


def validate_supplier_share_limit(supplier_share: float, share_limit: float) -> None:
    """
    Validate supplier share doesn't exceed concentration limit

    Anti-capture mechanism: prevents single supplier monopolization.

    Args:
        supplier_share: Supplier's current share (0.0-1.0)
        share_limit: Maximum allowed share (0.0-1.0)

    Raises:
        SupplierShareExceededError: If share exceeds limit
    """
    if supplier_share > share_limit:
        raise SupplierShareExceededError(
            f"Supplier share {supplier_share:.2%} exceeds limit {share_limit:.2%} - "
            f"excluded from rotation for diversification"
        )


def validate_random_seed_verifiable(seed: str | None) -> None:
    """
    Validate random seed is provided and non-empty

    Auditable randomness requires verifiable seed.

    Args:
        seed: Random seed for selection

    Raises:
        RandomSeedRequiredError: If seed missing or empty
    """
    if seed is None or not str(seed).strip():
        raise RandomSeedRequiredError(
            "Random seed required for auditable random selection"
        )


# ============================================================================
# Delivery & Reputation Validation
# ============================================================================


# Critical milestone types that require evidence
CRITICAL_MILESTONE_TYPES = {"completed", "test_passed", "test_failed"}


def validate_milestone_evidence(milestone_type: str, evidence: list[Any]) -> None:
    """
    Validate critical milestones have evidence

    Critical milestones (completed, test_passed) require supporting evidence.

    Args:
        milestone_type: Type of milestone
        evidence: Evidence items

    Raises:
        MilestoneEvidenceRequiredError: If critical milestone lacks evidence
    """
    if milestone_type in CRITICAL_MILESTONE_TYPES:
        if not evidence or len(evidence) == 0:
            raise MilestoneEvidenceRequiredError(
                f"Critical milestone '{milestone_type}' requires evidence"
            )


def validate_quality_score_range(score: float) -> None:
    """
    Validate quality score is in valid range [0.0, 1.0]

    Args:
        score: Quality score to validate

    Raises:
        InvalidQualityScoreError: If score out of range
    """
    if score < 0.0 or score > 1.0:
        raise InvalidQualityScoreError(
            f"Quality score must be between 0.0 and 1.0, got {score}"
        )


def validate_reputation_bounds(reputation: float) -> None:
    """
    Validate reputation score is in valid range [0.0, 1.0]

    Args:
        reputation: Reputation score to validate

    Raises:
        InvalidReputationScoreError: If reputation out of range
    """
    if reputation < 0.0 or reputation > 1.0:
        raise InvalidReputationScoreError(
            f"Reputation score must be between 0.0 and 1.0, got {reputation}"
        )
