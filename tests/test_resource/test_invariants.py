"""
Invariant Tests for Resource Module

Test-driven development: write tests first, then implement invariants.
Target: 100% coverage of all validation logic.

Fun fact: The practice of writing tests before code dates back to the 1950s
when NASA engineers tested rocket systems on paper before building hardware!
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from freedom_that_lasts.resource.invariants import (
    CapabilityClaimNotUniqueError,
    EvidenceExpiredError,
    EvidenceRequiredError,
    FeasibleSetEmptyError,
    InvalidQualityScoreError,
    InvalidReputationScoreError,
    InvalidSelectionMethodError,
    InvalidTenderRequirementError,
    LawNotActiveForProcurementError,
    MilestoneEvidenceRequiredError,
    RandomSeedRequiredError,
    SupplierNotInFeasibleSetError,
    SupplierShareExceededError,
    validate_capability_claim_unique,
    validate_evidence_not_expired,
    validate_evidence_required,
    validate_feasible_set_not_empty,
    validate_milestone_evidence,
    validate_quality_score_range,
    validate_random_seed_verifiable,
    validate_reputation_bounds,
    validate_selection_method,
    validate_supplier_in_feasible_set,
    validate_supplier_share_limit,
    validate_tender_requirements,
)
from freedom_that_lasts.resource.models import Evidence, SelectionMethod


# ============================================================================
# Evidence & Capability Validation Tests
# ============================================================================


class TestValidateEvidenceRequired:
    """Test evidence requirement validation"""

    def test_evidence_list_with_items_passes(self):
        """Valid evidence list should pass"""
        evidence = [
            Evidence(
                evidence_id="e1",
                evidence_type="certification",
                issuer="ISO",
                issued_at=datetime.now(),
            )
        ]
        # Should not raise
        validate_evidence_required(evidence)

    def test_multiple_evidence_items_passes(self):
        """Multiple evidence items should pass"""
        evidence = [
            Evidence(
                evidence_id="e1",
                evidence_type="certification",
                issuer="ISO",
                issued_at=datetime.now(),
            ),
            Evidence(
                evidence_id="e2",
                evidence_type="audit_report",
                issuer="Auditor",
                issued_at=datetime.now(),
            ),
        ]
        validate_evidence_required(evidence)

    def test_empty_evidence_list_raises_error(self):
        """Empty evidence list should raise EvidenceRequiredError"""
        with pytest.raises(EvidenceRequiredError) as exc_info:
            validate_evidence_required([])
        assert "at least one evidence" in str(exc_info.value).lower()

    def test_none_evidence_raises_error(self):
        """None evidence should raise EvidenceRequiredError"""
        with pytest.raises(EvidenceRequiredError):
            validate_evidence_required(None)


class TestValidateEvidenceNotExpired:
    """Test evidence expiration validation"""

    def test_non_expiring_evidence_passes(self):
        """Evidence with no expiry should pass"""
        evidence = Evidence(
            evidence_id="e1",
            evidence_type="certification",
            issuer="ISO",
            issued_at=datetime.now(),
            valid_until=None,  # No expiry
        )
        check_time = datetime.now() + timedelta(days=1000)
        # Should not raise
        validate_evidence_not_expired(evidence, check_time)

    def test_future_expiry_passes(self):
        """Evidence expiring in future should pass"""
        now = datetime.now()
        evidence = Evidence(
            evidence_id="e1",
            evidence_type="certification",
            issuer="ISO",
            issued_at=now,
            valid_until=now + timedelta(days=365),
        )
        check_time = now + timedelta(days=100)
        validate_evidence_not_expired(evidence, check_time)

    def test_exact_expiry_time_passes(self):
        """Evidence checked at exact expiry time should pass (not after)"""
        now = datetime.now()
        evidence = Evidence(
            evidence_id="e1",
            evidence_type="certification",
            issuer="ISO",
            issued_at=now,
            valid_until=now + timedelta(days=365),
        )
        check_time = now + timedelta(days=365)
        validate_evidence_not_expired(evidence, check_time)

    def test_expired_evidence_raises_error(self):
        """Expired evidence should raise EvidenceExpiredError"""
        now = datetime.now()
        evidence = Evidence(
            evidence_id="e1",
            evidence_type="certification",
            issuer="ISO",
            issued_at=now - timedelta(days=400),
            valid_until=now - timedelta(days=30),  # Expired 30 days ago
        )
        check_time = now
        with pytest.raises(EvidenceExpiredError) as exc_info:
            validate_evidence_not_expired(evidence, check_time)
        assert "expired" in str(exc_info.value).lower()

    def test_one_second_after_expiry_raises_error(self):
        """Evidence checked one second after expiry should raise error"""
        now = datetime.now()
        evidence = Evidence(
            evidence_id="e1",
            evidence_type="certification",
            issuer="ISO",
            issued_at=now,
            valid_until=now + timedelta(days=365),
        )
        check_time = now + timedelta(days=365, seconds=1)
        with pytest.raises(EvidenceExpiredError):
            validate_evidence_not_expired(evidence, check_time)


class TestValidateCapabilityClaimUnique:
    """Test capability claim uniqueness validation"""

    def test_new_capability_type_passes(self):
        """Adding new capability type should pass"""
        existing_capabilities = {
            "ISO27001": {"capability_type": "ISO27001"},
            "24_7_support": {"capability_type": "24_7_support"},
        }
        new_capability_type = "EU_procurement"
        # Should not raise
        validate_capability_claim_unique(existing_capabilities, new_capability_type)

    def test_empty_capabilities_passes(self):
        """First capability claim should pass"""
        validate_capability_claim_unique({}, "ISO27001")

    def test_duplicate_capability_type_raises_error(self):
        """Duplicate capability type should raise error"""
        existing_capabilities = {
            "ISO27001": {"capability_type": "ISO27001"},
        }
        with pytest.raises(CapabilityClaimNotUniqueError) as exc_info:
            validate_capability_claim_unique(existing_capabilities, "ISO27001")
        assert "already has capability" in str(exc_info.value).lower()
        assert "ISO27001" in str(exc_info.value)


# ============================================================================
# Tender Requirement Validation Tests
# ============================================================================


class TestValidateTenderRequirements:
    """Test tender requirement validation"""

    def test_valid_requirements_pass(self):
        """Well-formed requirements should pass"""
        requirements = [
            {
                "requirement_id": "r1",
                "capability_type": "ISO27001",
                "mandatory": True,
            },
            {
                "requirement_id": "r2",
                "capability_type": "24_7_support",
                "min_capacity": {"response_time_minutes": 30},
                "mandatory": True,
            },
        ]
        # Should not raise
        validate_tender_requirements(requirements)

    def test_single_requirement_passes(self):
        """Single requirement should pass"""
        requirements = [
            {"requirement_id": "r1", "capability_type": "ISO27001", "mandatory": True}
        ]
        validate_tender_requirements(requirements)

    def test_empty_requirements_raises_error(self):
        """Empty requirements should raise error"""
        with pytest.raises(InvalidTenderRequirementError) as exc_info:
            validate_tender_requirements([])
        assert "at least one requirement" in str(exc_info.value).lower()

    def test_missing_capability_type_raises_error(self):
        """Requirement without capability_type should raise error"""
        requirements = [
            {"requirement_id": "r1", "mandatory": True}  # Missing capability_type
        ]
        with pytest.raises(InvalidTenderRequirementError) as exc_info:
            validate_tender_requirements(requirements)
        assert "capability_type" in str(exc_info.value).lower()

    def test_empty_capability_type_raises_error(self):
        """Empty capability_type should raise error"""
        requirements = [
            {
                "requirement_id": "r1",
                "capability_type": "",  # Empty
                "mandatory": True,
            }
        ]
        with pytest.raises(InvalidTenderRequirementError):
            validate_tender_requirements(requirements)


# ============================================================================
# Feasible Set Validation Tests
# ============================================================================


class TestValidateFeasibleSetNotEmpty:
    """Test feasible set emptiness validation"""

    def test_non_empty_feasible_set_passes(self):
        """Non-empty feasible set should pass"""
        feasible_suppliers = ["supplier-1", "supplier-2", "supplier-3"]
        # Should not raise
        validate_feasible_set_not_empty(feasible_suppliers)

    def test_single_supplier_passes(self):
        """Single feasible supplier should pass"""
        validate_feasible_set_not_empty(["supplier-1"])

    def test_empty_feasible_set_raises_error(self):
        """Empty feasible set should raise error"""
        with pytest.raises(FeasibleSetEmptyError) as exc_info:
            validate_feasible_set_not_empty([])
        assert "no suppliers" in str(exc_info.value).lower()

    def test_none_feasible_set_raises_error(self):
        """None feasible set should raise error"""
        with pytest.raises(FeasibleSetEmptyError):
            validate_feasible_set_not_empty(None)


# ============================================================================
# Selection Validation Tests
# ============================================================================


class TestValidateSelectionMethod:
    """Test selection method validation"""

    def test_matching_selection_method_passes(self):
        """Matching selection method should pass"""
        validate_selection_method(
            SelectionMethod.ROTATION, SelectionMethod.ROTATION
        )
        validate_selection_method(
            SelectionMethod.RANDOM, SelectionMethod.RANDOM
        )
        validate_selection_method(
            SelectionMethod.ROTATION_WITH_RANDOM,
            SelectionMethod.ROTATION_WITH_RANDOM,
        )

    def test_mismatched_selection_method_raises_error(self):
        """Mismatched selection method should raise error"""
        with pytest.raises(InvalidSelectionMethodError) as exc_info:
            validate_selection_method(
                SelectionMethod.ROTATION, SelectionMethod.RANDOM
            )
        assert "does not match" in str(exc_info.value).lower()

    def test_error_includes_both_methods(self):
        """Error should include both expected and actual methods"""
        with pytest.raises(InvalidSelectionMethodError) as exc_info:
            validate_selection_method(
                SelectionMethod.RANDOM, SelectionMethod.ROTATION_WITH_RANDOM
            )
        error_msg = str(exc_info.value)
        assert "RANDOM" in error_msg
        assert "ROTATION_WITH_RANDOM" in error_msg


class TestValidateSupplierInFeasibleSet:
    """Test supplier feasible set membership validation"""

    def test_supplier_in_feasible_set_passes(self):
        """Supplier in feasible set should pass"""
        feasible_set = ["supplier-1", "supplier-2", "supplier-3"]
        validate_supplier_in_feasible_set("supplier-2", feasible_set)

    def test_first_supplier_passes(self):
        """First supplier in set should pass"""
        validate_supplier_in_feasible_set("supplier-1", ["supplier-1", "supplier-2"])

    def test_last_supplier_passes(self):
        """Last supplier in set should pass"""
        validate_supplier_in_feasible_set("supplier-3", ["supplier-1", "supplier-2", "supplier-3"])

    def test_supplier_not_in_feasible_set_raises_error(self):
        """Supplier not in feasible set should raise error"""
        feasible_set = ["supplier-1", "supplier-2"]
        with pytest.raises(SupplierNotInFeasibleSetError) as exc_info:
            validate_supplier_in_feasible_set("supplier-999", feasible_set)
        assert "not in feasible set" in str(exc_info.value).lower()
        assert "supplier-999" in str(exc_info.value)

    def test_empty_feasible_set_raises_error(self):
        """Empty feasible set should raise error"""
        with pytest.raises(SupplierNotInFeasibleSetError):
            validate_supplier_in_feasible_set("supplier-1", [])


class TestValidateSupplierShareLimit:
    """Test supplier share limit validation"""

    def test_below_limit_passes(self):
        """Supplier below share limit should pass"""
        supplier_share = 0.15  # 15%
        share_limit = 0.35  # 35% limit
        # Should not raise
        validate_supplier_share_limit(supplier_share, share_limit)

    def test_at_limit_passes(self):
        """Supplier at exact share limit should pass"""
        validate_supplier_share_limit(0.35, 0.35)

    def test_zero_share_passes(self):
        """Zero share should pass"""
        validate_supplier_share_limit(0.0, 0.35)

    def test_above_limit_raises_error(self):
        """Supplier above share limit should raise error"""
        supplier_share = 0.40  # 40%
        share_limit = 0.35  # 35% limit
        with pytest.raises(SupplierShareExceededError) as exc_info:
            validate_supplier_share_limit(supplier_share, share_limit)
        assert "exceeds" in str(exc_info.value).lower()

    def test_error_includes_share_and_limit(self):
        """Error should include both share and limit"""
        with pytest.raises(SupplierShareExceededError) as exc_info:
            validate_supplier_share_limit(0.45, 0.35)
        error_msg = str(exc_info.value)
        assert "45" in error_msg or "0.45" in error_msg
        assert "35" in error_msg or "0.35" in error_msg


class TestValidateRandomSeedVerifiable:
    """Test random seed verifiability validation"""

    def test_provided_seed_passes(self):
        """Provided seed should pass"""
        validate_random_seed_verifiable("hash-of-tender-and-time-123")

    def test_numeric_seed_passes(self):
        """Numeric seed should pass"""
        validate_random_seed_verifiable("12345")

    def test_complex_seed_passes(self):
        """Complex hash seed should pass"""
        validate_random_seed_verifiable(
            "sha256-abc123def456-tender-id-evaluation-time"
        )

    def test_none_seed_raises_error(self):
        """None seed should raise error"""
        with pytest.raises(RandomSeedRequiredError) as exc_info:
            validate_random_seed_verifiable(None)
        assert "required" in str(exc_info.value).lower()

    def test_empty_seed_raises_error(self):
        """Empty seed should raise error"""
        with pytest.raises(RandomSeedRequiredError):
            validate_random_seed_verifiable("")

    def test_whitespace_seed_raises_error(self):
        """Whitespace-only seed should raise error"""
        with pytest.raises(RandomSeedRequiredError):
            validate_random_seed_verifiable("   ")


# ============================================================================
# Delivery & Reputation Validation Tests
# ============================================================================


class TestValidateMilestoneEvidence:
    """Test milestone evidence validation"""

    def test_critical_milestone_with_evidence_passes(self):
        """Critical milestone with evidence should pass"""
        milestone_type = "completed"
        evidence = [
            {
                "evidence_id": "e1",
                "evidence_type": "test_result",
                "issuer": "QA",
                "issued_at": datetime.now().isoformat(),
            }
        ]
        # Should not raise
        validate_milestone_evidence(milestone_type, evidence)

    def test_test_passed_with_evidence_passes(self):
        """test_passed milestone with evidence should pass"""
        milestone_type = "test_passed"
        evidence = [{"evidence_id": "e1", "evidence_type": "test_result", "issuer": "QA", "issued_at": datetime.now().isoformat()}]
        validate_milestone_evidence(milestone_type, evidence)

    def test_non_critical_milestone_without_evidence_passes(self):
        """Non-critical milestone without evidence should pass"""
        milestone_type = "progress"
        evidence = []
        validate_milestone_evidence(milestone_type, evidence)

    def test_started_milestone_without_evidence_passes(self):
        """started milestone without evidence should pass"""
        validate_milestone_evidence("started", [])

    def test_critical_milestone_without_evidence_raises_error(self):
        """Critical milestone without evidence should raise error"""
        milestone_type = "completed"
        evidence = []
        with pytest.raises(MilestoneEvidenceRequiredError) as exc_info:
            validate_milestone_evidence(milestone_type, evidence)
        assert "requires evidence" in str(exc_info.value).lower()
        assert "completed" in str(exc_info.value).lower()

    def test_test_passed_without_evidence_raises_error(self):
        """test_passed without evidence should raise error"""
        with pytest.raises(MilestoneEvidenceRequiredError):
            validate_milestone_evidence("test_passed", [])


class TestValidateQualityScoreRange:
    """Test quality score range validation"""

    def test_zero_score_passes(self):
        """Quality score of 0.0 should pass"""
        validate_quality_score_range(0.0)

    def test_one_score_passes(self):
        """Quality score of 1.0 should pass"""
        validate_quality_score_range(1.0)

    def test_mid_score_passes(self):
        """Quality score of 0.5 should pass"""
        validate_quality_score_range(0.5)

    def test_high_score_passes(self):
        """Quality score of 0.95 should pass"""
        validate_quality_score_range(0.95)

    def test_negative_score_raises_error(self):
        """Negative quality score should raise error"""
        with pytest.raises(InvalidQualityScoreError) as exc_info:
            validate_quality_score_range(-0.1)
        assert "0.0 and 1.0" in str(exc_info.value)

    def test_above_one_score_raises_error(self):
        """Quality score above 1.0 should raise error"""
        with pytest.raises(InvalidQualityScoreError):
            validate_quality_score_range(1.1)

    def test_way_above_one_raises_error(self):
        """Way above 1.0 should raise error"""
        with pytest.raises(InvalidQualityScoreError):
            validate_quality_score_range(5.0)


class TestValidateReputationBounds:
    """Test reputation score bounds validation"""

    def test_zero_reputation_passes(self):
        """Reputation of 0.0 should pass"""
        validate_reputation_bounds(0.0)

    def test_one_reputation_passes(self):
        """Reputation of 1.0 should pass"""
        validate_reputation_bounds(1.0)

    def test_mid_reputation_passes(self):
        """Reputation of 0.5 should pass"""
        validate_reputation_bounds(0.5)

    def test_new_supplier_default_passes(self):
        """Default reputation of 0.5 for new suppliers should pass"""
        validate_reputation_bounds(0.5)

    def test_negative_reputation_raises_error(self):
        """Negative reputation should raise error"""
        with pytest.raises(InvalidReputationScoreError) as exc_info:
            validate_reputation_bounds(-0.1)
        assert "0.0 and 1.0" in str(exc_info.value)

    def test_above_one_reputation_raises_error(self):
        """Reputation above 1.0 should raise error"""
        with pytest.raises(InvalidReputationScoreError):
            validate_reputation_bounds(1.5)
