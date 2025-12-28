"""
Test Helper Functions - Builders and Assertions

Provides reusable builders for test data creation and custom assertions
for complex data structures. Follows the Builder pattern for test clarity.

Fun fact: The Builder pattern was formalized by the Gang of Four in 1994,
but test data builders were popularized by the growing programmer test
movement in the 2000s - we use them to keep tests readable and maintainable!
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from freedom_that_lasts.resource.models import SelectionMethod, TenderStatus


def create_supplier_with_capabilities(
    supplier_id: str,
    capabilities: dict[str, dict[str, Any]],
    total_value: Decimal = Decimal("0"),
    reputation: float = 0.5,
    name: str | None = None,
) -> dict[str, Any]:
    """
    Builder for test suppliers with capabilities

    Args:
        supplier_id: Unique supplier identifier
        capabilities: Dictionary of capability_type → capability_data
        total_value: Total contract value awarded (for rotation testing)
        reputation: Reputation score 0.0-1.0 (for threshold testing)
        name: Optional supplier name (defaults to "Supplier {supplier_id}")

    Returns:
        Supplier dictionary compatible with SupplierRegistry

    Example:
        >>> supplier = create_supplier_with_capabilities(
        ...     "s1",
        ...     {
        ...         "ISO27001": {
        ...             "capability_type": "ISO27001",
        ...             "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        ...             "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
        ...             "evidence": [...],
        ...             "verified": True,
        ...         }
        ...     },
        ...     total_value=Decimal("100000"),
        ...     reputation=0.85
        ... )
    """
    return {
        "supplier_id": supplier_id,
        "name": name or f"Supplier {supplier_id}",
        "capabilities": capabilities,
        "reputation_score": reputation,
        "total_value_awarded": total_value,
    }


def create_evidence(
    evidence_id: str,
    evidence_type: str = "certification",
    issuer: str = "Test Certification Body",
    issued_at: datetime | None = None,
    valid_until: datetime | None = None,
) -> dict[str, Any]:
    """
    Builder for evidence items

    Args:
        evidence_id: Unique evidence identifier
        evidence_type: Type of evidence (certification, audit_report, etc.)
        issuer: Who issued the evidence
        issued_at: When issued (defaults to 2024-12-01 UTC)
        valid_until: When expires (defaults to None = no expiry)

    Returns:
        Evidence dictionary

    Fun fact: The concept of expiring credentials dates back to medieval
    guild systems where apprentices needed to re-certify their skills periodically!
    """
    if issued_at is None:
        issued_at = datetime(2024, 12, 1, tzinfo=timezone.utc)

    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "issuer": issuer,
        "issued_at": issued_at,
        "valid_until": valid_until,
    }


def create_capability(
    capability_type: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
    evidence: list[dict] | None = None,
    verified: bool = True,
    capacity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Builder for capability claims

    Args:
        capability_type: Capability identifier (ISO27001, 50_welders, etc.)
        valid_from: Claim validity start date
        valid_until: Claim expiration (None = no expiry)
        evidence: List of evidence items (defaults to one certification)
        verified: Has evidence been validated?
        capacity: Capacity constraints (throughput, limits, etc.)

    Returns:
        Capability claim dictionary

    Example:
        >>> cap = create_capability(
        ...     "ISO27001",
        ...     datetime(2025, 1, 1, tzinfo=timezone.utc),
        ...     datetime(2026, 1, 1, tzinfo=timezone.utc),
        ...     verified=True,
        ...     capacity={"concurrent_projects": 5}
        ... )
    """
    if evidence is None:
        evidence = [
            create_evidence(
                "ev-default",
                valid_until=valid_until,
            )
        ]

    return {
        "capability_type": capability_type,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "evidence": evidence,
        "verified": verified,
        "capacity": capacity,
    }


def create_requirement(
    requirement_id: str,
    capability_type: str,
    min_capacity: dict[str, Any] | None = None,
    mandatory: bool = True,
) -> dict[str, Any]:
    """
    Builder for tender requirements

    Args:
        requirement_id: Unique requirement identifier
        capability_type: Required capability type
        min_capacity: Minimum capacity requirements (optional)
        mandatory: Is this requirement mandatory?

    Returns:
        Requirement dictionary

    Example:
        >>> req = create_requirement(
        ...     "req-1",
        ...     "ISO27001",
        ...     min_capacity={"concurrent_projects": 3},
        ...     mandatory=True
        ... )
    """
    return {
        "requirement_id": requirement_id,
        "capability_type": capability_type,
        "min_capacity": min_capacity,
        "mandatory": mandatory,
    }


def create_tender_with_requirements(
    tender_id: str,
    law_id: str,
    requirements: list[dict[str, Any]],
    selection_method: SelectionMethod = SelectionMethod.ROTATION,
    status: TenderStatus = TenderStatus.DRAFT,
    created_at: datetime | None = None,
    required_capacity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Builder for tenders

    Args:
        tender_id: Unique tender identifier
        law_id: Linked law ID
        requirements: List of requirement dictionaries
        selection_method: Constitutional selection mechanism
        status: Current tender status
        created_at: Creation timestamp (defaults to 2025-01-15 UTC)
        required_capacity: Overall capacity requirements (optional)

    Returns:
        Tender dictionary

    Example:
        >>> tender = create_tender_with_requirements(
        ...     "t-1",
        ...     "law-123",
        ...     [
        ...         create_requirement("r1", "ISO27001"),
        ...         create_requirement("r2", "GDPR_Compliant"),
        ...     ],
        ...     selection_method=SelectionMethod.ROTATION_WITH_RANDOM
        ... )
    """
    if created_at is None:
        created_at = datetime(2025, 1, 15, tzinfo=timezone.utc)

    return {
        "tender_id": tender_id,
        "law_id": law_id,
        "title": f"Test Tender {tender_id}",
        "description": f"Description for {tender_id}",
        "requirements": requirements,
        "required_capacity": required_capacity,
        "selection_method": selection_method,
        "status": status,
        "feasible_suppliers": [],
        "selected_supplier_id": None,
        "created_at": created_at,
    }


def assert_feasible_set(
    actual: list[str],
    expected: list[str],
    excluded: list[str] | None = None,
) -> None:
    """
    Custom assertion for feasible set computation

    Args:
        actual: Actual feasible supplier IDs
        expected: Expected feasible supplier IDs
        excluded: Expected excluded supplier IDs (optional)

    Raises:
        AssertionError: If feasible sets don't match

    Fun fact: Custom assertions improve test readability - a principle from
    the Behavior-Driven Development movement of the late 2000s!
    """
    actual_set = set(actual)
    expected_set = set(expected)

    if actual_set != expected_set:
        missing = expected_set - actual_set
        unexpected = actual_set - expected_set
        msg = f"Feasible set mismatch:\n"
        if missing:
            msg += f"  Missing: {sorted(missing)}\n"
        if unexpected:
            msg += f"  Unexpected: {sorted(unexpected)}\n"
        msg += f"  Expected: {sorted(expected)}\n"
        msg += f"  Actual: {sorted(actual)}"
        raise AssertionError(msg)

    if excluded is not None:
        # Additional check: ensure excluded suppliers are NOT in feasible set
        excluded_in_actual = set(excluded) & actual_set
        if excluded_in_actual:
            raise AssertionError(
                f"Excluded suppliers found in feasible set: {sorted(excluded_in_actual)}"
            )


def assert_exclusion_reasons(
    excluded_suppliers: list[dict[str, Any]],
    supplier_id: str,
    expected_reasons_substring: list[str],
) -> None:
    """
    Assert that excluded supplier has expected exclusion reasons

    Args:
        excluded_suppliers: List of {supplier_id, reasons} dicts
        supplier_id: Supplier to check
        expected_reasons_substring: Substrings that should appear in reasons

    Raises:
        AssertionError: If reasons don't match

    Example:
        >>> assert_exclusion_reasons(
        ...     excluded,
        ...     "s1",
        ...     ["Missing required capability", "ISO27001"]
        ... )
    """
    excluded_dict = {e["supplier_id"]: e["reasons"] for e in excluded_suppliers}

    if supplier_id not in excluded_dict:
        raise AssertionError(
            f"Supplier {supplier_id} not in excluded list. "
            f"Excluded: {list(excluded_dict.keys())}"
        )

    reasons = excluded_dict[supplier_id]
    reasons_text = " ".join(reasons)

    for substring in expected_reasons_substring:
        if substring not in reasons_text:
            raise AssertionError(
                f"Expected reason substring '{substring}' not found in reasons.\n"
                f"Supplier: {supplier_id}\n"
                f"Reasons: {reasons}"
            )


def create_balanced_suppliers_for_rotation(
    count: int = 3,
    base_load: Decimal = Decimal("100000"),
    variance: Decimal = Decimal("5000"),
) -> list[dict[str, Any]]:
    """
    Create suppliers with balanced loads for rotation testing

    Args:
        count: Number of suppliers to create
        base_load: Base total_value_awarded
        variance: Load variance between suppliers

    Returns:
        List of supplier dicts with incrementing loads

    Example:
        >>> suppliers = create_balanced_suppliers_for_rotation(3)
        >>> # Creates s0: 100k, s1: 105k, s2: 110k
    """
    suppliers = []
    for i in range(count):
        suppliers.append({
            "supplier_id": f"s{i}",
            "name": f"Supplier {i}",
            "total_value_awarded": base_load + (variance * i),
            "reputation_score": 0.75,
            "capabilities": {},
        })
    return suppliers
