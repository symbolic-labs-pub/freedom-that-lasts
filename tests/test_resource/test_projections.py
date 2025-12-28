"""
Tests for resource projections

Tests event-sourced read models for constitutional procurement.
Projections rebuild state from events - no direct state mutation.

Fun fact: Event sourcing was used by banks as early as the 1970s with
ledger systems - every transaction was an immutable event!
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.resource.models import TenderStatus, SelectionMethod
from freedom_that_lasts.resource.projections import (
    SupplierRegistry,
    TenderRegistry,
    DeliveryLog,
    ProcurementHealthProjection,
)


def create_event(
    event_id: str,
    stream_id: str,
    stream_type: str,
    event_type: str,
    occurred_at: datetime,
    command_id: str,
    actor_id: str,
    payload: dict,
    version: int,
) -> Event:
    """Helper to create events for testing"""
    return Event(
        event_id=event_id,
        stream_id=stream_id,
        stream_type=stream_type,
        event_type=event_type,
        occurred_at=occurred_at,
        command_id=command_id,
        actor_id=actor_id,
        payload=payload,
        version=version,
    )


# =============================================================================
# SupplierRegistry Tests
# =============================================================================


def test_supplier_registry_initial_state():
    """Test registry starts empty"""
    registry = SupplierRegistry()
    assert registry.suppliers == {}
    assert registry.list_all() == []


def test_supplier_registered_creates_entry(test_time):
    """Test SupplierRegistered event creates supplier with defaults"""
    registry = SupplierRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme Corp",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {"industry": "tech"},
        },
        version=1,
    )

    registry.apply_event(event)

    supplier = registry.get("s1")
    assert supplier is not None
    assert supplier["supplier_id"] == "s1"
    assert supplier["name"] == "Acme Corp"
    assert supplier["supplier_type"] == "general"
    assert supplier["reputation_score"] == 0.5  # Default for new suppliers
    assert supplier["total_value_awarded"] == Decimal("0")
    assert supplier["capabilities"] == {}
    assert supplier["metadata"] == {"industry": "tech"}
    assert supplier["version"] == 1


def test_capability_claim_added_creates_capability(test_time):
    """Test CapabilityClaimAdded adds capability to supplier"""
    registry = SupplierRegistry()

    # First register supplier
    register_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme Corp",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        },
        version=1,
    )
    registry.apply_event(register_event)

    # Add capability
    claim_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "claim_id": "claim-1",
            "capability_type": "ISO27001",
            "scope": "Information Security Management",
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "evidence": [{"evidence_type": "certification", "issuer": "BSI"}],
            "capacity": {"concurrent_projects": 5},
            "added_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(claim_event)

    supplier = registry.get("s1")
    assert "ISO27001" in supplier["capabilities"]
    capability = supplier["capabilities"]["ISO27001"]
    assert capability["claim_id"] == "claim-1"
    assert capability["capability_type"] == "ISO27001"
    assert capability["verified"] is True
    assert capability["capacity"] == {"concurrent_projects": 5}
    assert supplier["version"] == 2


def test_capability_claim_updated_modifies_evidence(test_time):
    """Test CapabilityClaimUpdated updates existing capability"""
    registry = SupplierRegistry()

    # Register supplier and add capability
    register_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        },
        version=1,
    )
    registry.apply_event(register_event)

    claim_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "claim_id": "claim-1",
            "capability_type": "ISO27001",
            "scope": "ISMS",
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "evidence": [{"old": "evidence"}],
            "capacity": {"projects": 5},
            "added_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(claim_event)

    # Update capability
    update_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimUpdated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "claim_id": "claim-1",
            "updated_evidence": [{"new": "evidence"}],
            "updated_validity": datetime(2027, 1, 1, tzinfo=timezone.utc),
            "updated_capacity": {"projects": 10},
            "updated_at": test_time.now().isoformat(),
        },
        version=3,
    )
    registry.apply_event(update_event)

    supplier = registry.get("s1")
    capability = supplier["capabilities"]["ISO27001"]
    assert capability["evidence"] == [{"new": "evidence"}]
    assert capability["valid_until"] == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert capability["capacity"] == {"projects": 10}
    assert supplier["version"] == 3


def test_capability_claim_revoked_removes_capability(test_time):
    """Test CapabilityClaimRevoked removes capability from supplier"""
    registry = SupplierRegistry()

    # Register supplier with capability
    register_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        },
        version=1,
    )
    registry.apply_event(register_event)

    claim_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "claim_id": "claim-1",
            "capability_type": "ISO27001",
            "scope": "ISMS",
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "evidence": [],
            "added_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(claim_event)

    # Revoke capability
    revoke_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimRevoked",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "capability_type": "ISO27001",
            "revoked_at": test_time.now().isoformat(),
            "reason": "Certification expired",
        },
        version=3,
    )
    registry.apply_event(revoke_event)

    supplier = registry.get("s1")
    assert "ISO27001" not in supplier["capabilities"]
    assert supplier["version"] == 3


def test_reputation_updated_changes_score(test_time):
    """Test ReputationUpdated event updates supplier reputation"""
    registry = SupplierRegistry()

    # Register supplier
    register_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        },
        version=1,
    )
    registry.apply_event(register_event)

    assert registry.get("s1")["reputation_score"] == 0.5

    # Update reputation
    reputation_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="ReputationUpdated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "supplier_id": "s1",
            "old_score": 0.5,
            "new_score": 0.75,
            "reason": "Completed tender t1 with quality 0.9",
            "tender_id": "t1",
            "updated_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(reputation_event)

    supplier = registry.get("s1")
    assert supplier["reputation_score"] == 0.75
    assert supplier["version"] == 2


def test_tender_awarded_accumulates_contract_value(test_time):
    """Test TenderAwarded event increments total_value_awarded"""
    registry = SupplierRegistry()

    # Register supplier
    register_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "name": "Acme",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        },
        version=1,
    )
    registry.apply_event(register_event)

    assert registry.get("s1")["total_value_awarded"] == Decimal("0")

    # Award first tender
    award_event1 = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderAwarded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "awarded_supplier_id": "s1",
            "contract_value": Decimal("100000"),
            "contract_terms": {},
            "awarded_at": test_time.now().isoformat(),
            "awarded_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(award_event1)

    assert registry.get("s1")["total_value_awarded"] == Decimal("100000")

    # Award second tender
    award_event2 = create_event(
        event_id=generate_id(),
        stream_id="t2",
        stream_type="Tender",
        event_type="TenderAwarded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t2",
            "awarded_supplier_id": "s1",
            "contract_value": "50000",  # String to test conversion
            "contract_terms": {},
            "awarded_at": test_time.now().isoformat(),
            "awarded_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(award_event2)

    assert registry.get("s1")["total_value_awarded"] == Decimal("150000")


def test_list_by_capability_filters_suppliers(test_time):
    """Test list_by_capability returns only suppliers with specific capability"""
    registry = SupplierRegistry()

    # Register two suppliers
    for supplier_id in ["s1", "s2"]:
        register_event = create_event(
            event_id=generate_id(),
            stream_id=supplier_id,
            stream_type="Supplier",
            event_type="SupplierRegistered",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload={
                "supplier_id": supplier_id,
                "name": f"Supplier {supplier_id}",
                "supplier_type": "general",
                "registered_at": test_time.now().isoformat(),
                "registered_by": "admin-1",
                "metadata": {},
            },
            version=1,
        )
        registry.apply_event(register_event)

    # Add ISO27001 to s1 only
    claim_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "s1",
            "claim_id": "claim-1",
            "capability_type": "ISO27001",
            "scope": "ISMS",
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "evidence": [],
            "added_at": test_time.now().isoformat(),
        },
        version=2,
    )
    registry.apply_event(claim_event)

    iso_suppliers = registry.list_by_capability("ISO27001")
    assert len(iso_suppliers) == 1
    assert iso_suppliers[0]["supplier_id"] == "s1"

    # No suppliers with SOC2
    soc2_suppliers = registry.list_by_capability("SOC2")
    assert len(soc2_suppliers) == 0


def test_supplier_registry_get_returns_none_for_missing():
    """Test get() returns None for nonexistent supplier"""
    registry = SupplierRegistry()
    assert registry.get("nonexistent") is None


def test_supplier_registry_defensive_against_missing_supplier(test_time):
    """Test event handlers are defensive when supplier doesn't exist"""
    registry = SupplierRegistry()

    # Try to add capability to nonexistent supplier
    claim_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "supplier_id": "nonexistent",
            "claim_id": "claim-1",
            "capability_type": "ISO27001",
            "scope": "ISMS",
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "evidence": [],
            "added_at": test_time.now().isoformat(),
        },
        version=1,
    )

    # Should not raise - defensive handling
    registry.apply_event(claim_event)
    assert registry.get("nonexistent") is None


# =============================================================================
# TenderRegistry Tests
# =============================================================================


def test_tender_registry_initial_state():
    """Test registry starts empty"""
    registry = TenderRegistry()
    assert registry.tenders == {}
    assert registry.list_active() == []


def test_tender_created_sets_draft_status(test_time):
    """Test TenderCreated event creates tender in DRAFT status"""
    registry = TenderRegistry()

    event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test Tender",
            "description": "Test description",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )

    registry.apply_event(event)

    tender = registry.get("t1")
    assert tender is not None
    assert tender["tender_id"] == "t1"
    assert tender["law_id"] == "law-123"
    assert tender["status"] == TenderStatus.DRAFT.value
    assert tender["requirements"] == []
    assert tender["feasible_suppliers"] == []
    assert tender["selected_supplier_id"] is None
    assert tender["version"] == 1


def test_tender_opened_changes_status_to_open(test_time):
    """Test TenderOpened event transitions status to OPEN"""
    registry = TenderRegistry()

    # Create tender
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Open tender
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "opened_at": test_time.now().isoformat(),
            "opened_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(opened_event)

    tender = registry.get("t1")
    assert tender["status"] == TenderStatus.OPEN.value
    assert tender["version"] == 2


def test_feasible_set_computed_sets_status_and_suppliers(test_time):
    """Test FeasibleSetComputed event sets EVALUATING status and feasible suppliers"""
    registry = TenderRegistry()

    # Create and open tender
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Compute feasible set
    feasible_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="FeasibleSetComputed",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "feasible_suppliers": ["s1", "s2", "s3"],
            "excluded_suppliers_with_reasons": [],
            "evaluation_time": test_time.now().isoformat(),
            "total_suppliers_evaluated": 3,
            "computation_method": "binary_requirement_matching",
            "computed_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(feasible_event)

    tender = registry.get("t1")
    assert tender["status"] == TenderStatus.EVALUATING.value
    assert tender["feasible_suppliers"] == ["s1", "s2", "s3"]
    assert tender["version"] == 2


def test_supplier_selected_sets_selected_supplier(test_time):
    """Test SupplierSelected event sets selected_supplier_id"""
    registry = TenderRegistry()

    # Create tender and compute feasible set
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Select supplier
    selected_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="SupplierSelected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "selected_supplier_id": "s1",
            "selection_method": SelectionMethod.ROTATION.value,
            "selection_reason": "Rotation: supplier with lowest load",
            "rotation_state": {"supplier_loads": {"s1": "100000"}},
            "random_seed": None,
            "selected_at": test_time.now().isoformat(),
            "selected_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(selected_event)

    tender = registry.get("t1")
    assert tender["selected_supplier_id"] == "s1"
    assert tender["version"] == 2


def test_tender_awarded_sets_status_and_contract_value(test_time):
    """Test TenderAwarded event sets AWARDED status and contract value"""
    registry = TenderRegistry()

    # Create tender
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Award tender
    awarded_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderAwarded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "awarded_supplier_id": "s1",
            "contract_value": Decimal("250000"),
            "contract_terms": {"duration_months": 12},
            "awarded_at": test_time.now().isoformat(),
            "awarded_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(awarded_event)

    tender = registry.get("t1")
    assert tender["status"] == TenderStatus.AWARDED.value
    assert tender["contract_value"] == Decimal("250000")
    assert tender["contract_terms"] == {"duration_months": 12}
    assert tender["version"] == 2


def test_tender_completed_sets_status_and_quality_score(test_time):
    """Test TenderCompleted event sets COMPLETED status and quality score"""
    registry = TenderRegistry()

    # Create tender
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Complete tender
    completed_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "final_quality_score": 0.85,
            "completion_report": {"summary": "Excellent work"},
            "completed_at": test_time.now().isoformat(),
            "completed_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(completed_event)

    tender = registry.get("t1")
    assert tender["status"] == TenderStatus.COMPLETED.value
    assert tender["final_quality_score"] == 0.85
    assert tender["version"] == 2


def test_tender_cancelled_sets_status(test_time):
    """Test TenderCancelled event sets CANCELLED status"""
    registry = TenderRegistry()

    # Create tender
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Cancel tender
    cancelled_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCancelled",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "reason": "Budget constraints",
            "cancelled_at": test_time.now().isoformat(),
            "cancelled_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(cancelled_event)

    tender = registry.get("t1")
    assert tender["status"] == TenderStatus.CANCELLED.value
    assert tender["version"] == 2


def test_list_by_law_filters_tenders(test_time):
    """Test list_by_law returns only tenders for specific law"""
    registry = TenderRegistry()

    # Create tenders for different laws
    for tender_id, law_id in [("t1", "law-1"), ("t2", "law-2"), ("t3", "law-1")]:
        event = create_event(
            event_id=generate_id(),
            stream_id=tender_id,
            stream_type="Tender",
            event_type="TenderCreated",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload={
                "tender_id": tender_id,
                "law_id": law_id,
                "title": f"Tender {tender_id}",
                "description": "Test",
                "requirements": [],
                "selection_method": SelectionMethod.ROTATION.value,
                "created_at": test_time.now().isoformat(),
                "created_by": "admin-1",
            },
            version=1,
        )
        registry.apply_event(event)

    law1_tenders = registry.list_by_law("law-1")
    assert len(law1_tenders) == 2
    assert {t["tender_id"] for t in law1_tenders} == {"t1", "t3"}

    law2_tenders = registry.list_by_law("law-2")
    assert len(law2_tenders) == 1
    assert law2_tenders[0]["tender_id"] == "t2"


def test_list_by_status_filters_tenders(test_time):
    """Test list_by_status returns only tenders with specific status"""
    registry = TenderRegistry()

    # Create tender in DRAFT
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event)

    # Create and complete another tender
    created_event2 = create_event(
        event_id=generate_id(),
        stream_id="t2",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t2",
            "law_id": "law-123",
            "title": "Test",
            "description": "Test",
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "created_at": test_time.now().isoformat(),
            "created_by": "admin-1",
        },
        version=1,
    )
    registry.apply_event(created_event2)

    completed_event = create_event(
        event_id=generate_id(),
        stream_id="t2",
        stream_type="Tender",
        event_type="TenderCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t2",
            "final_quality_score": 0.9,
            "completion_report": {},
            "completed_at": test_time.now().isoformat(),
            "completed_by": "admin-1",
        },
        version=2,
    )
    registry.apply_event(completed_event)

    draft_tenders = registry.list_by_status(TenderStatus.DRAFT)
    assert len(draft_tenders) == 1
    assert draft_tenders[0]["tender_id"] == "t1"

    completed_tenders = registry.list_by_status("COMPLETED")
    assert len(completed_tenders) == 1
    assert completed_tenders[0]["tender_id"] == "t2"


def test_list_active_excludes_completed_and_cancelled(test_time):
    """Test list_active returns only non-terminal status tenders"""
    registry = TenderRegistry()

    # Create tenders in different states
    statuses_and_ids = [
        ("t1", TenderStatus.DRAFT),
        ("t2", TenderStatus.OPEN),
        ("t3", TenderStatus.COMPLETED),
        ("t4", TenderStatus.CANCELLED),
    ]

    for tender_id, final_status in statuses_and_ids:
        # Create
        created_event = create_event(
            event_id=generate_id(),
            stream_id=tender_id,
            stream_type="Tender",
            event_type="TenderCreated",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload={
                "tender_id": tender_id,
                "law_id": "law-123",
                "title": "Test",
                "description": "Test",
                "requirements": [],
                "selection_method": SelectionMethod.ROTATION.value,
                "created_at": test_time.now().isoformat(),
                "created_by": "admin-1",
            },
            version=1,
        )
        registry.apply_event(created_event)

        # Transition to final status if needed
        if final_status == TenderStatus.OPEN:
            opened_event = create_event(
                event_id=generate_id(),
                stream_id=tender_id,
                stream_type="Tender",
                event_type="TenderOpened",
                occurred_at=test_time.now(),
                command_id=generate_id(),
                actor_id="admin-1",
                payload={
                    "tender_id": tender_id,
                    "opened_at": test_time.now().isoformat(),
                    "opened_by": "admin-1",
                },
                version=2,
            )
            registry.apply_event(opened_event)
        elif final_status == TenderStatus.COMPLETED:
            completed_event = create_event(
                event_id=generate_id(),
                stream_id=tender_id,
                stream_type="Tender",
                event_type="TenderCompleted",
                occurred_at=test_time.now(),
                command_id=generate_id(),
                actor_id="admin-1",
                payload={
                    "tender_id": tender_id,
                    "final_quality_score": 0.9,
                    "completion_report": {},
                    "completed_at": test_time.now().isoformat(),
                    "completed_by": "admin-1",
                },
                version=2,
            )
            registry.apply_event(completed_event)
        elif final_status == TenderStatus.CANCELLED:
            cancelled_event = create_event(
                event_id=generate_id(),
                stream_id=tender_id,
                stream_type="Tender",
                event_type="TenderCancelled",
                occurred_at=test_time.now(),
                command_id=generate_id(),
                actor_id="admin-1",
                payload={
                    "tender_id": tender_id,
                    "reason": "Test",
                    "cancelled_at": test_time.now().isoformat(),
                    "cancelled_by": "admin-1",
                },
                version=2,
            )
            registry.apply_event(cancelled_event)

    active_tenders = registry.list_active()
    assert len(active_tenders) == 1  # Only OPEN (DRAFT is not active)
    assert {t["tender_id"] for t in active_tenders} == {"t2"}


def test_tender_registry_get_returns_none_for_missing():
    """Test get() returns None for nonexistent tender"""
    registry = TenderRegistry()
    assert registry.get("nonexistent") is None


# =============================================================================
# DeliveryLog Tests
# =============================================================================


def test_delivery_log_initial_state():
    """Test delivery log starts empty"""
    log = DeliveryLog()
    assert log.get_by_tender("t1") == {"milestones": [], "sla_breaches": [], "completions": []}


def test_milestone_recorded_adds_milestone(test_time):
    """Test MilestoneRecorded event adds milestone to tender log"""
    log = DeliveryLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="MilestoneRecorded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "milestone_id": "m1",
            "milestone_type": "inspection",
            "description": "Quality inspection passed",
            "evidence": [],
            "recorded_at": test_time.now().isoformat(),
            "metadata": {"inspector": "QA Team"},
        },
        version=1,
    )

    log.apply_event(event)

    tender_log = log.get_by_tender("t1")
    assert len(tender_log["milestones"]) == 1
    milestone = tender_log["milestones"][0]
    assert milestone["milestone_id"] == "m1"
    assert milestone["milestone_type"] == "inspection"
    assert milestone["description"] == "Quality inspection passed"
    assert milestone["metadata"] == {"inspector": "QA Team"}


def test_sla_breach_detected_adds_breach(test_time):
    """Test SLABreachDetected event adds breach to tender log"""
    log = DeliveryLog()

    event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="SLABreachDetected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "tender_id": "t1",
            "sla_metric": "delivery_time",
            "expected_value": "10 days",
            "actual_value": "12 days",
            "severity": "medium",
            "impact_description": "Delivery missed by 2 days",
            "detected_at": test_time.now().isoformat(),
        },
        version=1,
    )

    log.apply_event(event)

    tender_log = log.get_by_tender("t1")
    assert len(tender_log["sla_breaches"]) == 1
    breach = tender_log["sla_breaches"][0]
    assert breach["sla_metric"] == "delivery_time"
    assert breach["severity"] == "medium"
    assert breach["impact_description"] == "Delivery missed by 2 days"


def test_tender_completed_marks_tender_complete(test_time):
    """Test TenderCompleted event marks tender as completed in log"""
    log = DeliveryLog()

    # Record milestone first
    milestone_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="MilestoneRecorded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "milestone_id": "m1",
            "milestone_type": "started",
            "description": "Work started",
            "evidence": [],
            "recorded_at": test_time.now().isoformat(),
            "metadata": {},
        },
        version=1,
    )
    log.apply_event(milestone_event)

    # Complete tender
    completed_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCompleted",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "final_quality_score": 0.9,
            "completion_report": {},
            "completed_at": test_time.now().isoformat(),
            "completed_by": "admin-1",
        },
        version=2,
    )
    log.apply_event(completed_event)

    tender_log = log.get_by_tender("t1")
    assert len(tender_log["completions"]) == 1
    completion = tender_log["completions"][0]
    assert completion["final_quality_score"] == 0.9


def test_get_milestones_returns_only_milestones(test_time):
    """Test get_milestones returns only milestone entries"""
    log = DeliveryLog()

    # Add milestone
    milestone_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="MilestoneRecorded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "milestone_id": "m1",
            "milestone_type": "started",
            "description": "Started",
            "evidence": [],
            "recorded_at": test_time.now().isoformat(),
            "metadata": {},
        },
        version=1,
    )
    log.apply_event(milestone_event)

    # Add SLA breach
    breach_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="SLABreachDetected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "tender_id": "t1",
            "sla_metric": "delivery_time",
            "expected_value": "5 days",
            "actual_value": "6 days",
            "severity": "low",
            "impact_description": "Minor delay",
            "detected_at": test_time.now().isoformat(),
        },
        version=2,
    )
    log.apply_event(breach_event)

    milestones = log.get_milestones("t1")
    assert len(milestones) == 1
    assert milestones[0]["milestone_id"] == "m1"


def test_get_sla_breaches_returns_only_breaches(test_time):
    """Test get_sla_breaches returns only breach entries"""
    log = DeliveryLog()

    # Add milestone
    milestone_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="MilestoneRecorded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload={
            "tender_id": "t1",
            "milestone_id": "m1",
            "milestone_type": "started",
            "description": "Started",
            "evidence": [],
            "recorded_at": test_time.now().isoformat(),
            "metadata": {},
        },
        version=1,
    )
    log.apply_event(milestone_event)

    # Add SLA breach
    breach_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="SLABreachDetected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "tender_id": "t1",
            "sla_metric": "delivery_time",
            "expected_value": "5 days",
            "actual_value": "6 days",
            "severity": "low",
            "impact_description": "Minor delay",
            "detected_at": test_time.now().isoformat(),
        },
        version=2,
    )
    log.apply_event(breach_event)

    breaches = log.get_sla_breaches("t1")
    assert len(breaches) == 1
    assert breaches[0]["sla_metric"] == "delivery_time"


# =============================================================================
# ProcurementHealthProjection Tests
# =============================================================================


def test_procurement_health_initial_state():
    """Test health projection starts with no issues"""
    health = ProcurementHealthProjection()
    assert health.has_issues() is False
    assert health.has_issues("t1") is False
    assert health.get_latest_concentration_warning() is None
    assert health.get_latest_concentration_halt() is None


def test_empty_feasible_set_detected_records_issue(test_time):
    """Test EmptyFeasibleSetDetected event records tender issue"""
    health = ProcurementHealthProjection()

    event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="EmptyFeasibleSetDetected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "requirements_summary": "ISO27001 certification required",
            "detected_at": test_time.now().isoformat(),
            "action_required": "Review requirements or expand supplier pool",
        },
        version=1,
    )

    health.apply_event(event)

    assert health.has_issues() is True
    assert health.has_issues("t1") is True
    assert health.has_issues("t2") is False


def test_concentration_warning_records_warning(test_time):
    """Test SupplierConcentrationWarning event records warning"""
    health = ProcurementHealthProjection()

    event = create_event(
        event_id=generate_id(),
        stream_id="market",
        stream_type="Market",
        event_type="SupplierConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "detected_at": test_time.now().isoformat(),
            "total_procurement_value": Decimal("1000000"),
            "supplier_shares": {"s1": 0.35, "s2": 0.30, "s3": 0.35},
            "gini_coefficient": 0.42,
            "top_supplier_id": "s1",
            "top_supplier_share": 0.35,
            "threshold_exceeded": 0.33,
        },
        version=1,
    )

    health.apply_event(event)

    assert health.has_issues() is True
    warning = health.get_latest_concentration_warning()
    assert warning is not None
    assert warning["top_supplier_id"] == "s1"
    assert warning["top_supplier_share"] == 0.35
    assert warning["gini_coefficient"] == 0.42


def test_concentration_halt_records_critical_issue(test_time):
    """Test SupplierConcentrationHalt event records critical issue"""
    health = ProcurementHealthProjection()

    event = create_event(
        event_id=generate_id(),
        stream_id="market",
        stream_type="Market",
        event_type="SupplierConcentrationHalt",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "detected_at": test_time.now().isoformat(),
            "total_procurement_value": Decimal("1000000"),
            "supplier_shares": {"s1": 0.55, "s2": 0.25, "s3": 0.20},
            "gini_coefficient": 0.62,
            "halted_supplier_id": "s1",
            "supplier_share": 0.55,
            "critical_threshold_exceeded": 0.5,
        },
        version=1,
    )

    health.apply_event(event)

    assert health.has_issues() is True
    halt = health.get_latest_concentration_halt()
    assert halt is not None
    assert halt["halted_supplier_id"] == "s1"
    assert halt["supplier_share"] == 0.55
    assert halt["critical_threshold_exceeded"] == 0.5


def test_latest_concentration_warning_returns_most_recent(test_time):
    """Test get_latest_concentration_warning returns most recent warning"""
    health = ProcurementHealthProjection()

    # Add first warning
    event1 = create_event(
        event_id=generate_id(),
        stream_id="market",
        stream_type="Market",
        event_type="SupplierConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "detected_at": test_time.now().isoformat(),
            "total_procurement_value": Decimal("1000000"),
            "supplier_shares": {"s1": 0.35, "s2": 0.30, "s3": 0.35},
            "gini_coefficient": 0.42,
            "top_supplier_id": "s1",
            "top_supplier_share": 0.35,
            "threshold_exceeded": 0.33,
        },
        version=1,
    )
    health.apply_event(event1)

    # Add second warning later
    test_time.advance_seconds(3600)  # Advance 1 hour
    event2 = create_event(
        event_id=generate_id(),
        stream_id="market",
        stream_type="Market",
        event_type="SupplierConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "detected_at": test_time.now().isoformat(),
            "total_procurement_value": Decimal("1000000"),
            "supplier_shares": {"s1": 0.30, "s2": 0.38, "s3": 0.32},
            "gini_coefficient": 0.45,
            "top_supplier_id": "s2",
            "top_supplier_share": 0.38,
            "threshold_exceeded": 0.33,
        },
        version=2,
    )
    health.apply_event(event2)

    latest = health.get_latest_concentration_warning()
    assert latest["top_supplier_id"] == "s2"  # Most recent


def test_procurement_health_tracks_multiple_issues(test_time):
    """Test health projection tracks both empty sets and concentration issues"""
    health = ProcurementHealthProjection()

    # Empty feasible set for t1
    empty_set_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="EmptyFeasibleSetDetected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "tender_id": "t1",
            "law_id": "law-123",
            "requirements_summary": "No feasible suppliers found",
            "detected_at": test_time.now().isoformat(),
            "action_required": "Review requirements",
        },
        version=1,
    )
    health.apply_event(empty_set_event)

    # Concentration warning
    concentration_event = create_event(
        event_id=generate_id(),
        stream_id="market",
        stream_type="Market",
        event_type="SupplierConcentrationWarning",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload={
            "detected_at": test_time.now().isoformat(),
            "total_procurement_value": Decimal("1000000"),
            "supplier_shares": {"s1": 0.35, "s2": 0.30, "s3": 0.35},
            "gini_coefficient": 0.42,
            "top_supplier_id": "s1",
            "top_supplier_share": 0.35,
            "threshold_exceeded": 0.33,
        },
        version=1,
    )
    health.apply_event(concentration_event)

    assert health.has_issues() is True
    assert health.has_issues("t1") is True
    assert health.get_latest_concentration_warning() is not None
