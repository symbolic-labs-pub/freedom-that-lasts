"""
Tests for Resource Domain Models

Tests Pydantic validation, business logic methods, and edge cases for:
- Evidence (verification expiration)
- CapabilityClaim (time-based validity, evidence expiration)
- Supplier (capability checking with multiple failure modes)
- TenderRequirement (validation)
- Tender (validation)

Fun fact: Pydantic validation is named after the Latin "pydanticus" meaning
"extremely pedantic" - perfect for catching domain rule violations!
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from freedom_that_lasts.resource.models import (
    Evidence,
    CapabilityClaim,
    Supplier,
    TenderRequirement,
    Tender,
    TenderStatus,
    SelectionMethod,
)


# =============================================================================
# Evidence Model Tests
# =============================================================================


def test_evidence_valid_creation():
    """Test Evidence can be created with valid data"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO Certification Body",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, tzinfo=timezone.utc),
        document_uri="https://example.com/cert.pdf",
        metadata={"cert_number": "ISO-12345"},
    )

    assert evidence.evidence_id == "ev-1"
    assert evidence.evidence_type == "certification"
    assert evidence.issuer == "ISO Certification Body"


def test_evidence_type_empty_raises():
    """Test Evidence rejects empty evidence_type"""
    with pytest.raises(ValidationError) as exc_info:
        Evidence(
            evidence_id="ev-1",
            evidence_type="",  # Empty!
            issuer="ISO",
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Evidence type cannot be empty" in str(exc_info.value)


def test_evidence_type_whitespace_raises():
    """Test Evidence rejects whitespace-only evidence_type"""
    with pytest.raises(ValidationError) as exc_info:
        Evidence(
            evidence_id="ev-1",
            evidence_type="   ",  # Whitespace only!
            issuer="ISO",
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Evidence type cannot be empty" in str(exc_info.value)


def test_evidence_issuer_empty_raises():
    """Test Evidence rejects empty issuer"""
    with pytest.raises(ValidationError) as exc_info:
        Evidence(
            evidence_id="ev-1",
            evidence_type="certification",
            issuer="",  # Empty!
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Evidence issuer cannot be empty" in str(exc_info.value)


def test_evidence_issuer_whitespace_raises():
    """Test Evidence rejects whitespace-only issuer"""
    with pytest.raises(ValidationError) as exc_info:
        Evidence(
            evidence_id="ev-1",
            evidence_type="certification",
            issuer="   ",  # Whitespace only!
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Evidence issuer cannot be empty" in str(exc_info.value)


def test_evidence_is_expired_no_expiry():
    """Test Evidence without expiry never expires"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=None,  # No expiry
    )

    # Should never expire, even far in the future
    future = datetime(2099, 12, 31, tzinfo=timezone.utc)
    assert evidence.is_expired(future) is False


def test_evidence_is_expired_before_expiry():
    """Test Evidence is not expired before valid_until"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    # Check one day before expiry
    before_expiry = datetime(2024, 12, 31, tzinfo=timezone.utc)
    assert evidence.is_expired(before_expiry) is False


def test_evidence_is_expired_after_expiry():
    """Test Evidence is expired after valid_until"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    # Check one day after expiry
    after_expiry = datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert evidence.is_expired(after_expiry) is True


def test_evidence_is_expired_exactly_at_expiry():
    """Test Evidence at exact expiry time is not expired (boundary)"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    # Exactly at expiry time
    exactly_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert evidence.is_expired(exactly_at) is False


# =============================================================================
# CapabilityClaim Model Tests
# =============================================================================


def test_capability_claim_valid_creation():
    """Test CapabilityClaim can be created with valid data"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="certification",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={"territory": "EU", "sectors": ["finance", "healthcare"]},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
        verified=True,
        capacity={"concurrent_projects": 5, "annual_audits": 20},
    )

    assert claim.claim_id == "claim-1"
    assert claim.capability_type == "ISO27001"
    assert claim.verified is True


def test_capability_claim_capability_type_empty_raises():
    """Test CapabilityClaim rejects empty capability_type"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValidationError) as exc_info:
        CapabilityClaim(
            claim_id="claim-1",
            supplier_id="s1",
            capability_type="",  # Empty!
            scope={},
            valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            evidence=[evidence],
        )

    assert "Capability type cannot be empty" in str(exc_info.value)


def test_capability_claim_empty_evidence_raises():
    """Test CapabilityClaim rejects empty evidence list"""
    with pytest.raises(ValidationError) as exc_info:
        CapabilityClaim(
            claim_id="claim-1",
            supplier_id="s1",
            capability_type="ISO27001",
            scope={},
            valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            evidence=[],  # Empty evidence list!
        )

    # Pydantic's built-in min_length validation
    assert "at least 1 item" in str(exc_info.value).lower()


def test_capability_claim_is_valid_at_within_period():
    """Test CapabilityClaim is valid within valid_from and valid_until"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
    )

    # Check in the middle of validity period
    check_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert claim.is_valid_at(check_time) is True


def test_capability_claim_is_valid_at_before_valid_from():
    """Test CapabilityClaim is invalid before valid_from"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
    )

    # Check before valid_from
    before = datetime(2024, 12, 31, tzinfo=timezone.utc)
    assert claim.is_valid_at(before) is False


def test_capability_claim_is_valid_at_after_valid_until():
    """Test CapabilityClaim is invalid after valid_until"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
    )

    # Check after valid_until
    after = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert claim.is_valid_at(after) is False


def test_capability_claim_is_valid_at_no_expiry():
    """Test CapabilityClaim with no expiry is valid after valid_from"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,  # No expiry
        evidence=[evidence],
    )

    # Should be valid far in the future
    future = datetime(2099, 12, 31, tzinfo=timezone.utc)
    assert claim.is_valid_at(future) is True


def test_capability_claim_has_expired_evidence_none_expired():
    """Test CapabilityClaim with all valid evidence"""
    evidence1 = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    evidence2 = Evidence(
        evidence_id="ev-2",
        evidence_type="audit",
        issuer="Auditor",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=None,  # No expiry
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence1, evidence2],
    )

    # Check when all evidence is still valid
    check_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert claim.has_expired_evidence(check_time) is False


def test_capability_claim_has_expired_evidence_one_expired():
    """Test CapabilityClaim with at least one expired evidence"""
    evidence1 = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 6, 1, tzinfo=timezone.utc),  # Expires soon
    )
    evidence2 = Evidence(
        evidence_id="ev-2",
        evidence_type="audit",
        issuer="Auditor",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence1, evidence2],
    )

    # Check after first evidence expired
    check_time = datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert claim.has_expired_evidence(check_time) is True


# =============================================================================
# Supplier Model Tests
# =============================================================================


def test_supplier_valid_creation():
    """Test Supplier can be created with valid data"""
    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        reputation_score=0.75,
        total_value_awarded=Decimal("100000"),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        metadata={"location": "EU", "employees": 50},
    )

    assert supplier.supplier_id == "s1"
    assert supplier.name == "Acme Corp"
    assert supplier.reputation_score == 0.75


def test_supplier_name_empty_raises():
    """Test Supplier rejects empty name"""
    with pytest.raises(ValidationError) as exc_info:
        Supplier(
            supplier_id="s1",
            name="",  # Empty!
            supplier_type="company",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Supplier name cannot be empty" in str(exc_info.value)


def test_supplier_type_empty_raises():
    """Test Supplier rejects empty supplier_type"""
    with pytest.raises(ValidationError) as exc_info:
        Supplier(
            supplier_id="s1",
            name="Acme Corp",
            supplier_type="",  # Empty!
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    assert "Supplier type cannot be empty" in str(exc_info.value)


def test_supplier_has_capability_not_claimed():
    """Test Supplier.has_capability returns False when capability not claimed"""
    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capabilities={},  # No capabilities
    )

    check_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    has_cap, reason = supplier.has_capability("ISO27001", check_time)

    assert has_cap is False
    assert "not claimed" in reason


def test_supplier_has_capability_claim_expired():
    """Test Supplier.has_capability returns False when claim expired"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, tzinfo=timezone.utc),  # Expires
        evidence=[evidence],
        verified=True,
    )

    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capabilities={"ISO27001": claim},
    )

    # Check after claim expired
    check_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
    has_cap, reason = supplier.has_capability("ISO27001", check_time)

    assert has_cap is False
    assert "expired or not yet valid" in reason


def test_supplier_has_capability_evidence_expired():
    """Test Supplier.has_capability returns False when evidence expired"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2025, 1, 1, tzinfo=timezone.utc),  # Evidence expires
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),  # Claim valid
        evidence=[evidence],
        verified=True,
    )

    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capabilities={"ISO27001": claim},
    )

    # Check after evidence expired (but claim still valid)
    check_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
    has_cap, reason = supplier.has_capability("ISO27001", check_time)

    assert has_cap is False
    assert "expired evidence" in reason


def test_supplier_has_capability_not_verified():
    """Test Supplier.has_capability returns False when evidence not verified"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
        verified=False,  # Not verified!
    )

    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capabilities={"ISO27001": claim},
    )

    check_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    has_cap, reason = supplier.has_capability("ISO27001", check_time)

    assert has_cap is False
    assert "not yet verified" in reason


def test_supplier_has_capability_success():
    """Test Supplier.has_capability returns True for valid capability"""
    evidence = Evidence(
        evidence_id="ev-1",
        evidence_type="cert",
        issuer="ISO",
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    claim = CapabilityClaim(
        claim_id="claim-1",
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[evidence],
        verified=True,
    )

    supplier = Supplier(
        supplier_id="s1",
        name="Acme Corp",
        supplier_type="company",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capabilities={"ISO27001": claim},
    )

    check_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    has_cap, reason = supplier.has_capability("ISO27001", check_time)

    assert has_cap is True
    assert reason is None


# =============================================================================
# TenderRequirement Model Tests
# =============================================================================


def test_tender_requirement_valid_creation():
    """Test TenderRequirement can be created with valid data"""
    requirement = TenderRequirement(
        requirement_id="req-1",
        capability_type="ISO27001",
        min_capacity={"concurrent_projects": 5},
        mandatory=True,
    )

    assert requirement.requirement_id == "req-1"
    assert requirement.capability_type == "ISO27001"
    assert requirement.mandatory is True


def test_tender_requirement_capability_type_empty_raises():
    """Test TenderRequirement rejects empty capability_type"""
    with pytest.raises(ValidationError) as exc_info:
        TenderRequirement(
            requirement_id="req-1",
            capability_type="",  # Empty!
            mandatory=True,
        )

    assert "Capability type cannot be empty" in str(exc_info.value)


# =============================================================================
# Tender Model Tests
# =============================================================================


def test_tender_valid_creation():
    """Test Tender can be created with valid data"""
    requirement = TenderRequirement(
        requirement_id="req-1",
        capability_type="ISO27001",
    )

    tender = Tender(
        tender_id="t1",
        law_id="law-123",
        title="Security Audit Services",
        description="Annual security audit",
        requirements=[requirement],
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    assert tender.tender_id == "t1"
    assert tender.title == "Security Audit Services"
    assert tender.status == TenderStatus.DRAFT


def test_tender_title_empty_raises():
    """Test Tender rejects empty title"""
    requirement = TenderRequirement(
        requirement_id="req-1",
        capability_type="ISO27001",
    )

    with pytest.raises(ValidationError) as exc_info:
        Tender(
            tender_id="t1",
            law_id="law-123",
            title="",  # Empty!
            description="Test",
            requirements=[requirement],
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    assert "Tender title cannot be empty" in str(exc_info.value)


def test_tender_empty_requirements_raises():
    """Test Tender rejects empty requirements list"""
    with pytest.raises(ValidationError) as exc_info:
        Tender(
            tender_id="t1",
            law_id="law-123",
            title="Test Tender",
            description="Test",
            requirements=[],  # Empty!
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    # Pydantic's built-in min_length validation
    assert "at least 1 item" in str(exc_info.value).lower()
