"""
Tests for Feasible Set Computation - Binary Requirement Matching

Core constitutional procurement logic: binary yes/no matching with NO scoring, NO weighting.
Supplier either meets ALL requirements or doesn't - no subjective evaluation.

Fun fact: Binary logic dates back to ancient Indian mathematician Pingala (300 BCE)
who developed the first binary number system - we're using it to prevent procurement
corruption 2300 years later!
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from freedom_that_lasts.resource.feasible import (
    compute_feasible_set,
    check_supplier_meets_requirement,
)
from tests.helpers import (
    create_supplier_with_capabilities,
    create_capability,
    create_requirement,
    create_evidence,
    assert_feasible_set,
    assert_exclusion_reasons,
)


# ==============================================================================
# Basic Capability Matching Tests
# ==============================================================================


def test_single_supplier_meets_single_requirement() -> None:
    """Test simple happy path: one supplier, one requirement, perfect match"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, ["s1"])
    assert len(excluded) == 0


def test_supplier_missing_mandatory_capability() -> None:
    """Test exclusion when supplier lacks mandatory capability"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["Missing required capability", "ISO27001"])


def test_supplier_meets_optional_requirement() -> None:
    """Test that optional requirements don't cause exclusion if missing"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirements = [
        create_requirement("r1", "ISO27001", mandatory=True),
        create_requirement("r2", "GDPR_Compliant", mandatory=False),  # Optional
    ]

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=requirements,
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should be feasible - optional requirement doesn't exclude
    assert_feasible_set(feasible, ["s1"])


def test_multiple_suppliers_partial_match() -> None:
    """Test that only suppliers meeting ALL requirements are feasible"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    s1 = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )

    s2 = create_supplier_with_capabilities(
        "s2",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            # Missing GDPR_Compliant
        },
    )

    requirements = [
        create_requirement("r1", "ISO27001", mandatory=True),
        create_requirement("r2", "GDPR_Compliant", mandatory=True),
    ]

    feasible, excluded = compute_feasible_set(
        suppliers=[s1, s2],
        requirements=requirements,
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, ["s1"], excluded=["s2"])
    assert_exclusion_reasons(excluded, "s2", ["Missing required capability", "GDPR_Compliant"])


# ==============================================================================
# Time Validity Tests
# ==============================================================================


def test_capability_not_yet_valid() -> None:
    """Test exclusion when capability valid_from is in the future"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 2, 1, tzinfo=timezone.utc),  # Future!
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["not yet valid", "valid from 2025-02-01"])


def test_capability_expired() -> None:
    """Test exclusion when capability valid_until is in the past"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2024, 12, 31, tzinfo=timezone.utc),  # Expired!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["expired", "valid until 2024-12-31"])


def test_capability_valid_on_exact_valid_from_date() -> None:
    """Test boundary condition: evaluation time exactly equals valid_from"""
    eval_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),  # Exact match
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should be feasible - valid_from is inclusive
    assert_feasible_set(feasible, ["s1"])


def test_capability_valid_one_second_before_expiry() -> None:
    """Test boundary condition: evaluation time just before valid_until"""
    eval_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should be feasible - still within validity period
    assert_feasible_set(feasible, ["s1"])


def test_capability_expired_on_exact_valid_until_date() -> None:
    """Test boundary condition: evaluation time exactly equals valid_until"""
    eval_time = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should be excluded - valid_until is exclusive (expired after that time)
    assert_feasible_set(feasible, [])


def test_capability_with_no_expiry() -> None:
    """Test capability without valid_until (never expires)"""
    eval_time = datetime(2030, 1, 1, tzinfo=timezone.utc)  # Far in future

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=None,  # No expiry!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should be feasible - no expiry means always valid (after valid_from)
    assert_feasible_set(feasible, ["s1"])


# ==============================================================================
# Evidence Expiration Tests
# ==============================================================================


def test_evidence_expired() -> None:
    """Test exclusion when evidence has expired"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    evidence = create_evidence(
        "ev-1",
        valid_until=datetime(2025, 5, 1, tzinfo=timezone.utc),  # Expired!
    )

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                evidence=[evidence],
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["expired evidence", "ev-1"])


def test_multiple_evidence_items_all_valid() -> None:
    """Test capability with multiple evidence items all valid"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    evidence = [
        create_evidence("ev-1", valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        create_evidence("ev-2", valid_until=datetime(2026, 6, 1, tzinfo=timezone.utc)),
        create_evidence("ev-3", valid_until=None),  # No expiry
    ]

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
                evidence=evidence,
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # All evidence valid - should be feasible
    assert_feasible_set(feasible, ["s1"])


def test_multiple_evidence_items_one_expired() -> None:
    """Test that ANY expired evidence invalidates capability"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    evidence = [
        create_evidence("ev-1", valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc)),  # Valid
        create_evidence("ev-2", valid_until=datetime(2025, 5, 1, tzinfo=timezone.utc)),  # Expired!
    ]

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
                evidence=evidence,
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # One expired evidence - should be excluded
    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["expired evidence", "ev-2"])


# ==============================================================================
# Evidence Verification Tests
# ==============================================================================


def test_evidence_not_verified() -> None:
    """Test exclusion when evidence exists but not verified"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                verified=False,  # Not verified!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["evidence not yet verified"])


def test_evidence_verified() -> None:
    """Test that verified evidence allows feasibility"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                verified=True,  # Verified!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", mandatory=True)

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Verified evidence - should be feasible
    assert_feasible_set(feasible, ["s1"])


# ==============================================================================
# Capacity Constraint Tests (Per-Requirement)
# ==============================================================================


def test_capacity_requirement_met() -> None:
    """Test that supplier with sufficient capacity is feasible"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 10, "annual_audits": 50},
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "ISO27001",
        min_capacity={"concurrent_projects": 5, "annual_audits": 20},
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Capacity exceeds requirements - should be feasible
    assert_feasible_set(feasible, ["s1"])


def test_capacity_requirement_insufficient() -> None:
    """Test exclusion when capacity is below requirement"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 3},  # Too low!
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "ISO27001",
        min_capacity={"concurrent_projects": 5},
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["insufficient capacity", "concurrent_projects=3 < 5"])


def test_capacity_missing_required_metric() -> None:
    """Test exclusion when capability lacks required capacity metric"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 10},  # Missing annual_audits
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "ISO27001",
        min_capacity={"concurrent_projects": 5, "annual_audits": 20},  # Requires both
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["missing capacity metric", "annual_audits"])


def test_capacity_no_capacity_data() -> None:
    """Test exclusion when capability has no capacity data but requirement needs it"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity=None,  # No capacity data!
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "ISO27001",
        min_capacity={"concurrent_projects": 5},
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["missing capacity data"])


def test_capacity_non_numeric_comparison() -> None:
    """Test capacity comparison for non-numeric values (string equality)"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"region": "EU", "dpo_certified": "yes"},
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "GDPR_Compliant",
        min_capacity={"region": "EU", "dpo_certified": "yes"},
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # String equality match - should be feasible
    assert_feasible_set(feasible, ["s1"])


def test_capacity_non_numeric_mismatch() -> None:
    """Test exclusion for non-numeric capacity mismatch"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"region": "US"},  # Wrong region!
            )
        },
    )

    requirement = create_requirement(
        "r1",
        "GDPR_Compliant",
        min_capacity={"region": "EU"},
    )

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["capacity mismatch", "region=US != EU"])


# ==============================================================================
# Overall Required Capacity Tests (Tender-Level)
# ==============================================================================


def test_overall_required_capacity_met() -> None:
    """Test that supplier meets overall tender capacity requirements"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"staff_count": 50},
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"staff_count": 30},  # Lower but acceptable
            ),
        },
    )

    requirements = [
        create_requirement("r1", "ISO27001"),
        create_requirement("r2", "GDPR_Compliant"),
    ]

    # Overall tender requires 40 staff (uses max across capabilities)
    required_capacity = {"staff_count": 40}

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=requirements,
        required_capacity=required_capacity,
        evaluation_time=eval_time,
    )

    # Max staff_count is 50 (from ISO27001) >= 40 required
    assert_feasible_set(feasible, ["s1"])


def test_overall_required_capacity_insufficient() -> None:
    """Test exclusion when overall capacity is below tender requirements"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"staff_count": 30},  # Too low!
            ),
        },
    )

    requirements = [create_requirement("r1", "ISO27001")]

    # Overall tender requires 50 staff
    required_capacity = {"staff_count": 50}

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=requirements,
        required_capacity=required_capacity,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["Insufficient overall capacity", "staff_count=30.0 < 50"])


def test_overall_required_capacity_missing_metric() -> None:
    """Test exclusion when supplier lacks required capacity metric entirely"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 10},  # Has this but not staff_count
            ),
        },
    )

    requirements = [create_requirement("r1", "ISO27001")]

    # Tender requires staff_count metric
    required_capacity = {"staff_count": 40}

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=requirements,
        required_capacity=required_capacity,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["missing required capacity metric", "staff_count"])


# ==============================================================================
# Complex Scenario Tests
# ==============================================================================


def test_multiple_suppliers_mixed_outcomes() -> None:
    """Test complex scenario with multiple suppliers and varied outcomes"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    # Supplier 1: Perfect match
    s1 = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 10},
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )

    # Supplier 2: Missing GDPR
    s2 = create_supplier_with_capabilities(
        "s2",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 10},
            ),
        },
    )

    # Supplier 3: Has both but ISO27001 expired
    s3 = create_supplier_with_capabilities(
        "s3",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2025, 5, 1, tzinfo=timezone.utc),  # Expired!
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )

    # Supplier 4: Has both but insufficient capacity
    s4 = create_supplier_with_capabilities(
        "s4",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 3},  # Too low!
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )

    # Supplier 5: Perfect match (second feasible supplier)
    s5 = create_supplier_with_capabilities(
        "s5",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
                capacity={"concurrent_projects": 15},
            ),
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )

    requirements = [
        create_requirement("r1", "ISO27001", min_capacity={"concurrent_projects": 5}),
        create_requirement("r2", "GDPR_Compliant"),
    ]

    feasible, excluded = compute_feasible_set(
        suppliers=[s1, s2, s3, s4, s5],
        requirements=requirements,
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Only s1 and s5 should be feasible
    assert_feasible_set(feasible, ["s1", "s5"], excluded=["s2", "s3", "s4"])

    # Verify specific exclusion reasons
    assert_exclusion_reasons(excluded, "s2", ["Missing required capability", "GDPR_Compliant"])
    assert_exclusion_reasons(excluded, "s3", ["expired", "ISO27001"])
    assert_exclusion_reasons(excluded, "s4", ["insufficient capacity", "concurrent_projects"])


def test_empty_suppliers_list() -> None:
    """Test edge case: no suppliers provided"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)
    requirements = [create_requirement("r1", "ISO27001")]

    feasible, excluded = compute_feasible_set(
        suppliers=[],
        requirements=requirements,
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert len(excluded) == 0


def test_empty_requirements_list() -> None:
    """Test edge case: no requirements (all suppliers feasible)"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    s1 = create_supplier_with_capabilities("s1", {})
    s2 = create_supplier_with_capabilities("s2", {})

    feasible, excluded = compute_feasible_set(
        suppliers=[s1, s2],
        requirements=[],  # No requirements
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # No requirements = all suppliers feasible (vacuous truth)
    assert_feasible_set(feasible, ["s1", "s2"])


# ==============================================================================
# Helper Function Tests (check_supplier_meets_requirement)
# ==============================================================================


def test_check_supplier_meets_requirement_true() -> None:
    """Test helper function for single supplier-requirement check (positive)"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is True
    assert reason is None


def test_check_supplier_meets_requirement_false() -> None:
    """Test helper function for single supplier-requirement check (negative)"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities("s1", {})  # No capabilities

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "Missing capability" in reason
    assert "ISO27001" in reason


def test_check_supplier_meets_requirement_not_yet_valid() -> None:
    """Test helper function detects not-yet-valid capability"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 2, 1, tzinfo=timezone.utc),  # Future!
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "not yet valid" in reason


def test_check_supplier_meets_requirement_expired_capability() -> None:
    """Test helper function detects expired capability"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2025, 5, 1, tzinfo=timezone.utc),  # Expired!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "expired" in reason


def test_check_supplier_meets_requirement_expired_evidence() -> None:
    """Test helper function detects expired evidence"""
    eval_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    evidence = create_evidence("ev-1", valid_until=datetime(2025, 5, 1, tzinfo=timezone.utc))

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                evidence=[evidence],
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "expired" in reason
    assert "ev-1" in reason


def test_check_supplier_meets_requirement_not_verified() -> None:
    """Test helper function detects unverified evidence"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                verified=False,  # Not verified!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001")

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "not yet verified" in reason


def test_check_supplier_meets_requirement_missing_capacity_data() -> None:
    """Test helper function detects missing capacity data"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity=None,  # No capacity!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", min_capacity={"projects": 5})

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "Missing capacity data" in reason


def test_check_supplier_meets_requirement_missing_capacity_metric() -> None:
    """Test helper function detects missing capacity metric"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"projects": 10},  # Missing "staff" metric
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", min_capacity={"projects": 5, "staff": 20})

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "Missing capacity metric" in reason
    assert "staff" in reason


def test_check_supplier_meets_requirement_insufficient_capacity() -> None:
    """Test helper function detects insufficient capacity"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "ISO27001": create_capability(
                "ISO27001",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"projects": 3},  # Too low!
            )
        },
    )

    requirement = create_requirement("r1", "ISO27001", min_capacity={"projects": 5})

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "Insufficient capacity" in reason
    assert "projects" in reason


def test_check_supplier_meets_requirement_capacity_mismatch() -> None:
    """Test helper function detects non-numeric capacity mismatch"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = create_supplier_with_capabilities(
        "s1",
        {
            "GDPR_Compliant": create_capability(
                "GDPR_Compliant",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
                capacity={"region": "US"},  # Wrong region!
            )
        },
    )

    requirement = create_requirement("r1", "GDPR_Compliant", min_capacity={"region": "EU"})

    meets, reason = check_supplier_meets_requirement(supplier, requirement, eval_time)

    assert meets is False
    assert "Capacity mismatch" in reason
    assert "region" in reason


# ==============================================================================
# String Date Parsing Tests
# ==============================================================================


def test_capability_with_string_dates() -> None:
    """Test that string dates are properly parsed (ISO format)"""
    eval_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Simulate data coming from JSON/API with string dates
    supplier = {
        "supplier_id": "s1",
        "capabilities": {
            "ISO27001": {
                "capability_type": "ISO27001",
                "valid_from": "2025-01-01T00:00:00+00:00",  # String!
                "valid_until": "2026-01-01T00:00:00+00:00",  # String!
                "evidence": [
                    {
                        "evidence_id": "ev-1",
                        "evidence_type": "certification",
                        "issuer": "ISO Body",
                        "issued_at": "2024-12-01T00:00:00+00:00",
                        "valid_until": "2026-01-01T00:00:00+00:00",  # String!
                    }
                ],
                "verified": True,
            }
        },
    }

    requirement = create_requirement("r1", "ISO27001")

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    # Should parse strings correctly and find supplier feasible
    assert_feasible_set(feasible, ["s1"])


def test_supplier_with_no_capabilities_dict() -> None:
    """Test supplier without capabilities key"""
    eval_time = datetime(2025, 1, 15, tzinfo=timezone.utc)

    supplier = {"supplier_id": "s1"}  # No capabilities key!

    requirement = create_requirement("r1", "ISO27001")

    feasible, excluded = compute_feasible_set(
        suppliers=[supplier],
        requirements=[requirement],
        required_capacity=None,
        evaluation_time=eval_time,
    )

    assert_feasible_set(feasible, [])
    assert_exclusion_reasons(excluded, "s1", ["Missing required capability", "ISO27001"])
