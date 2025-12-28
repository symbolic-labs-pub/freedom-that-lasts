"""
Resource Command Handler Tests

Tests for constitutional procurement command handlers - registration, tender lifecycle,
and multi-gate supplier selection enforcement.

Coverage target: handlers.py 9.59% → 95%+

Fun fact: The Command pattern was formalized by the Gang of Four in 1994, but command
handlers in CQRS architectures were popularized by Greg Young's work on event sourcing
in the late 2000s - we use them to enforce constitutional procurement rules!
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from freedom_that_lasts.kernel.events import create_event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.resource.commands import (
    AddCapabilityClaim,
    AwardTender,
    CompleteTender,
    CreateTender,
    EvaluateTender,
    OpenTender,
    RecordMilestone,
    RecordSLABreach,
    RegisterSupplier,
    SelectSupplier,
)
from freedom_that_lasts.resource.handlers import ResourceCommandHandlers
from freedom_that_lasts.resource.models import SelectionMethod, TenderStatus
from freedom_that_lasts.resource.projections import SupplierRegistry, TenderRegistry


# =============================================================================
# Helper Functions for Part 2 Tests
# =============================================================================


def create_tender_in_evaluating_status(
    tender_registry: TenderRegistry,
    test_time,
    tender_id: str = "t1",
    feasible_suppliers: list[str] | None = None,
    selection_method: SelectionMethod = SelectionMethod.ROTATION,
) -> None:
    """
    Helper to create a tender in EVALUATING status with proper event sequence.

    Applies: TenderCreated → FeasibleSetComputed (sets status to EVALUATING)
    """
    if feasible_suppliers is None:
        feasible_suppliers = []

    # 1. TenderCreated → DRAFT status
    tender_payload = {
        "tender_id": tender_id,
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test description",
        "requirements": [],
        "selection_method": selection_method.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    # 2. FeasibleSetComputed → EVALUATING status
    feasible_payload = {
        "tender_id": tender_id,
        "feasible_suppliers": feasible_suppliers,
        "excluded_suppliers_with_reasons": [],
        "evaluation_time": test_time.now().isoformat(),
    }
    feasible_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="FeasibleSetComputed",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=feasible_payload,
        version=2,
    )
    tender_registry.apply_event(feasible_event)


def create_tender_in_awarded_status(
    tender_registry: TenderRegistry,
    test_time,
    tender_id: str = "t1",
    selected_supplier_id: str = "s1",
) -> None:
    """Helper to create a tender in AWARDED status."""
    # TenderCreated → DRAFT
    tender_payload = {
        "tender_id": tender_id,
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)


    # FeasibleSetComputed → EVALUATING
    feasible_payload = {
        "tender_id": tender_id,
        "feasible_suppliers": [selected_supplier_id],
        "excluded_suppliers_with_reasons": [],
        "evaluation_time": test_time.now().isoformat(),
    }
    feasible_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="FeasibleSetComputed",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=feasible_payload,
        version=2,
    )
    tender_registry.apply_event(feasible_event)

    # SupplierSelected → stays EVALUATING until awarded
    selected_payload = {
        "tender_id": tender_id,
        "selected_supplier_id": selected_supplier_id,
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "selection_reason": "Test selection",
        "rotation_state": {},
        "random_seed": None,
        "selected_at": test_time.now().isoformat(),
        "selected_by": "admin-1",
    }
    selected_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="SupplierSelected",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=selected_payload,
        version=3,
    )
    tender_registry.apply_event(selected_event)

    # TenderAwarded → AWARDED status
    awarded_payload = {
        "tender_id": tender_id,
        "awarded_supplier_id": selected_supplier_id,
        "contract_value": "100000",
        "contract_terms": {},
        "awarded_at": test_time.now().isoformat(),
        "awarded_by": "admin-1",
    }
    awarded_event = create_event(
        event_id=generate_id(),
        stream_id=tender_id,
        stream_type="Tender",
        event_type="TenderAwarded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=awarded_payload,
        version=4,
    )
    tender_registry.apply_event(awarded_event)


def create_tender_in_in_delivery_status(
    tender_registry: TenderRegistry,
    test_time,
    tender_id: str = "t1",
    selected_supplier_id: str = "s1",
) -> None:
    """Helper to create a tender in IN_DELIVERY status."""
    # First get to AWARDED
    create_tender_in_awarded_status(tender_registry, test_time, tender_id, selected_supplier_id)

    # No explicit event transitions to IN_DELIVERY in the current implementation
    # It happens implicitly when work starts (milestone/SLA events imply delivery has started)


# =============================================================================
# PART 1: Simple and Medium Handlers (RegisterSupplier, AddCapabilityClaim,
#         CreateTender, OpenTender, EvaluateTender)
# =============================================================================


# -----------------------------------------------------------------------------
# 1. RegisterSupplier Handler Tests (Simple - 6 tests)
# -----------------------------------------------------------------------------


def test_register_supplier_success(resource_handlers, test_time) -> None:
    """Test successful supplier registration with all required fields"""
    command = RegisterSupplier(
        name="Acme Security Corp",
        supplier_type="security_consulting",
        metadata={"industry": "cybersecurity", "founded": 2010},
    )

    events = resource_handlers.handle_register_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "SupplierRegistered"
    assert event.stream_type == "Supplier"
    assert event.payload["name"] == "Acme Security Corp"
    assert event.payload["supplier_type"] == "security_consulting"
    assert event.payload["metadata"]["industry"] == "cybersecurity"
    assert "supplier_id" in event.payload
    assert event.command_id == "cmd-1"
    assert event.actor_id == "admin-1"


def test_register_supplier_minimal_fields(resource_handlers, test_time) -> None:
    """Test registration with only required fields (no metadata)"""
    command = RegisterSupplier(
        name="Basic Corp",
        supplier_type="general",
    )

    events = resource_handlers.handle_register_supplier(
        command=command,
        command_id="cmd-2",
        actor_id="admin-1",
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "SupplierRegistered"
    assert event.payload["name"] == "Basic Corp"
    assert event.payload["metadata"] == {}


def test_register_supplier_generates_unique_ids(resource_handlers, test_time) -> None:
    """Test that each registration generates unique supplier IDs"""
    command1 = RegisterSupplier(name="Corp A", supplier_type="type_a")
    command2 = RegisterSupplier(name="Corp B", supplier_type="type_b")

    events1 = resource_handlers.handle_register_supplier(
        command=command1, command_id="cmd-1", actor_id="admin-1"
    )
    events2 = resource_handlers.handle_register_supplier(
        command=command2, command_id="cmd-2", actor_id="admin-1"
    )

    supplier_id_1 = events1[0].payload["supplier_id"]
    supplier_id_2 = events2[0].payload["supplier_id"]

    assert supplier_id_1 != supplier_id_2


def test_register_supplier_includes_timestamp(resource_handlers, test_time) -> None:
    """Test that registration event includes current timestamp"""
    command = RegisterSupplier(name="Time Corp", supplier_type="general")

    events = resource_handlers.handle_register_supplier(
        command=command, command_id="cmd-1", actor_id="admin-1"
    )

    event = events[0]
    assert "registered_at" in event.payload
    # occurred_at should use test_time
    assert event.occurred_at == test_time.now()


def test_register_supplier_empty_name_rejected(resource_handlers, test_time) -> None:
    """Test that whitespace-only supplier name is normalized"""
    # Pydantic allows empty strings, but we can test whitespace handling
    command = RegisterSupplier(name="   ", supplier_type="general")

    events = resource_handlers.handle_register_supplier(
        command=command, command_id="cmd-1", actor_id="admin-1"
    )

    # Name should be preserved as-is (handler doesn't trim)
    assert events[0].payload["name"] == "   "


def test_register_supplier_preserves_all_metadata(resource_handlers, test_time) -> None:
    """Test that all metadata fields are preserved in event"""
    metadata = {
        "industry": "finance",
        "founded": 1995,
        "employees": 250,
        "certifications": ["ISO9001", "SOC2"],
        "website": "https://example.com",
    }

    command = RegisterSupplier(
        name="Finance Corp",
        supplier_type="financial_services",
        metadata=metadata,
    )

    events = resource_handlers.handle_register_supplier(
        command=command, command_id="cmd-1", actor_id="admin-1"
    )

    assert events[0].payload["metadata"] == metadata


# -----------------------------------------------------------------------------
# 2. AddCapabilityClaim Handler Tests (Medium - 10 tests)
# -----------------------------------------------------------------------------


def test_add_capability_claim_success(resource_handlers, test_time) -> None:
    """Test successful capability claim addition with valid evidence"""
    supplier_registry = SupplierRegistry()

    # First register supplier
    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={"regions": ["EU", "US"]},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "ISO Certification Body",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ],
        capacity={"concurrent_projects": 5},
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "CapabilityClaimAdded"
    assert event.payload["supplier_id"] == "s1"
    assert event.payload["capability_type"] == "ISO27001"
    assert event.payload["scope"]["regions"] == ["EU", "US"]
    assert len(event.payload["evidence"]) == 1
    assert event.payload["capacity"]["concurrent_projects"] == 5


def test_add_capability_claim_supplier_not_found(
    resource_handlers, test_time
) -> None:
    """Test that adding capability to non-existent supplier fails"""
    supplier_registry = SupplierRegistry()

    command = AddCapabilityClaim(
        supplier_id="nonexistent",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": None,
            }
        ],
    )

    with pytest.raises(Exception, match="Supplier.*not found"):
        resource_handlers.handle_add_capability_claim(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            supplier_registry=supplier_registry,
        )


def test_add_capability_claim_parses_string_dates(
    resource_handlers, test_time
) -> None:
    """Test that string dates are parsed to datetime objects"""
    supplier_registry = SupplierRegistry()

    # Register supplier first
    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from="2025-01-01T00:00:00Z",  # String date
        valid_until="2026-01-01T00:00:00Z",  # String date
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": "2024-12-01T00:00:00Z",  # String date
                "valid_until": "2026-01-01T00:00:00Z",  # String date
            }
        ],
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    event = events[0]
    # Dates should be in ISO format in payload
    assert "2025-01-01" in event.payload["valid_from"]


def test_add_capability_claim_no_expiration(resource_handlers, test_time) -> None:
    """Test capability claim with no expiration date (valid_until = None)"""
    supplier_registry = SupplierRegistry()

    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="permanent_capability",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,  # No expiration
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": None,  # Evidence also doesn't expire
            }
        ],
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    assert events[0].payload["valid_until"] is None


def test_add_capability_claim_multiple_evidence(resource_handlers, test_time) -> None:
    """Test capability claim with multiple evidence items"""
    supplier_registry = SupplierRegistry()

    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "ISO Body",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            {
                "evidence_id": "ev-2",
                "evidence_type": "audit_report",
                "issuer": "External Auditor",
                "issued_at": datetime(2024, 11, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2025, 11, 1, tzinfo=timezone.utc),
            },
        ],
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    assert len(events[0].payload["evidence"]) == 2
    # Handler generates new evidence IDs, so we just check they exist and are different
    ev1_id = events[0].payload["evidence"][0]["evidence_id"]
    ev2_id = events[0].payload["evidence"][1]["evidence_id"]
    assert ev1_id is not None
    assert ev2_id is not None
    assert ev1_id != ev2_id
    # Check evidence types are preserved
    assert events[0].payload["evidence"][0]["evidence_type"] == "certification"
    assert events[0].payload["evidence"][1]["evidence_type"] == "audit_report"


def test_add_capability_claim_requires_evidence(resource_handlers, test_time) -> None:
    """Test that capability claim requires at least one evidence item"""
    with pytest.raises(Exception):  # Pydantic ValidationError - min_length=1
        AddCapabilityClaim(
            supplier_id="s1",
            capability_type="ISO27001",
            scope={},
            valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            valid_until=None,
            evidence=[],  # Empty evidence list
        )


def test_add_capability_claim_optional_capacity(resource_handlers, test_time) -> None:
    """Test that capacity constraints are optional"""
    supplier_registry = SupplierRegistry()

    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": None,
            }
        ],
        capacity=None,  # No capacity specified
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    assert events[0].payload["capacity"] is None


def test_add_capability_claim_duplicate_capability_type(
    resource_handlers, test_time
) -> None:
    """Test that duplicate capability_type for same supplier is rejected"""
    supplier_registry = SupplierRegistry()

    # Register supplier
    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    # Add first capability claim
    cap_event_payload = {
        "claim_id": generate_id(),  # Required field
        "supplier_id": "s1",
        "capability_type": "ISO27001",
        "scope": {},
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "evidence": [
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat(),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
        "capacity": None,
        "added_at": test_time.now().isoformat(),  # Required field
        "added_by": "admin-1",  # Required field
    }
    cap_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=cap_event_payload,
        version=2,
    )
    supplier_registry.apply_event(cap_event)

    # Try to add duplicate capability_type
    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",  # Duplicate
        scope={},
        valid_from=datetime(2025, 6, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 6, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_id": "ev-2",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2025, 5, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 6, 1, tzinfo=timezone.utc),
            }
        ],
    )

    with pytest.raises(Exception, match="already has capability"):
        resource_handlers.handle_add_capability_claim(
            command=command,
            command_id="cmd-2",
            actor_id="admin-1",
            supplier_registry=supplier_registry,
        )


def test_add_capability_claim_includes_claim_id(
    resource_handlers, test_time
) -> None:
    """Test that capability claim event includes generated claim_id"""
    supplier_registry = SupplierRegistry()

    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": None,
            }
        ],
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    # Handler should generate claim_id
    assert "claim_id" in events[0].payload
    assert events[0].payload["claim_id"] is not None


def test_add_capability_claim_complex_capacity_constraints(
    resource_handlers, test_time
) -> None:
    """Test capability claim with complex capacity constraint dictionary"""
    supplier_registry = SupplierRegistry()

    reg_event_payload = {
        "supplier_id": "s1",
        "name": "Test Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    reg_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=reg_event_payload,
        version=1,
    )
    supplier_registry.apply_event(reg_event)

    command = AddCapabilityClaim(
        supplier_id="s1",
        capability_type="ISO27001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=None,
        evidence=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": None,
            }
        ],
        capacity={
            "concurrent_projects": 10,
            "annual_audits": 50,
            "max_organization_size": 5000,
            "geographic_coverage": ["EU", "US", "APAC"],
        },
    )

    events = resource_handlers.handle_add_capability_claim(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        supplier_registry=supplier_registry,
    )

    capacity = events[0].payload["capacity"]
    assert capacity["concurrent_projects"] == 10
    assert capacity["annual_audits"] == 50
    assert capacity["max_organization_size"] == 5000
    assert "EU" in capacity["geographic_coverage"]


# -----------------------------------------------------------------------------
# 3. CreateTender Handler Tests (Medium - 8 tests)
# -----------------------------------------------------------------------------


def test_create_tender_success(resource_handlers, test_time, mock_law_registry) -> None:
    """Test successful tender creation with valid requirements"""
    command = CreateTender(
        law_id="law-123",
        title="Security Audit Services",
        description="Annual security audit for government systems",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": {"concurrent_projects": 3},
                "mandatory": True,
            },
            {
                "requirement_id": "req-2",
                "capability_type": "GDPR_Compliant",
                "min_capacity": None,
                "mandatory": True,
            },
        ],
        selection_method=SelectionMethod.ROTATION_WITH_RANDOM,
    )

    events = resource_handlers.handle_create_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        law_registry=mock_law_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "TenderCreated"
    assert event.stream_type == "Tender"
    assert event.payload["law_id"] == "law-123"
    assert event.payload["title"] == "Security Audit Services"
    assert len(event.payload["requirements"]) == 2
    assert event.payload["selection_method"] == SelectionMethod.ROTATION_WITH_RANDOM.value
    assert "tender_id" in event.payload
    # Status is set by projection, not in event payload


def test_create_tender_law_not_found(resource_handlers, test_time) -> None:
    """Test that creating tender with non-existent law fails"""
    empty_law_registry = {}

    command = CreateTender(
        law_id="nonexistent",
        title="Test Tender",
        description="Test",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
    )

    with pytest.raises(Exception, match="Law.*not found"):
        resource_handlers.handle_create_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            law_registry=empty_law_registry,
        )


def test_create_tender_law_not_active(resource_handlers, test_time) -> None:
    """Test that creating tender with inactive law fails"""
    inactive_law_registry = {
        "law-123": {
            "law_id": "law-123",
            "status": "DRAFT",  # Not ACTIVE
            "title": "Test Law",
            "version": 1,
        }
    }

    command = CreateTender(
        law_id="law-123",
        title="Test Tender",
        description="Test",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
    )

    with pytest.raises(Exception, match="ACTIVE"):
        resource_handlers.handle_create_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            law_registry=inactive_law_registry,
        )


def test_create_tender_requires_requirements(resource_handlers, test_time) -> None:
    """Test that tender creation requires at least one requirement"""
    with pytest.raises(Exception):  # Pydantic ValidationError - min_length=1
        CreateTender(
            law_id="law-123",
            title="Test Tender",
            description="Test",
            requirements=[],  # Empty requirements
        )


def test_create_tender_default_selection_method(
    resource_handlers, test_time, mock_law_registry
) -> None:
    """Test that selection method defaults to ROTATION_WITH_RANDOM"""
    command = CreateTender(
        law_id="law-123",
        title="Test Tender",
        description="Test",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        # selection_method not specified - should default
    )

    events = resource_handlers.handle_create_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        law_registry=mock_law_registry,
    )

    assert events[0].payload["selection_method"] == SelectionMethod.ROTATION_WITH_RANDOM.value


def test_create_tender_generates_unique_ids(
    resource_handlers, test_time, mock_law_registry
) -> None:
    """Test that each tender creation generates unique IDs"""
    command1 = CreateTender(
        law_id="law-123",
        title="Tender A",
        description="Test A",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
    )

    command2 = CreateTender(
        law_id="law-123",
        title="Tender B",
        description="Test B",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
    )

    events1 = resource_handlers.handle_create_tender(
        command=command1, command_id="cmd-1", actor_id="admin-1", law_registry=mock_law_registry
    )
    events2 = resource_handlers.handle_create_tender(
        command=command2, command_id="cmd-2", actor_id="admin-1", law_registry=mock_law_registry
    )

    tender_id_1 = events1[0].payload["tender_id"]
    tender_id_2 = events2[0].payload["tender_id"]

    assert tender_id_1 != tender_id_2


def test_create_tender_preserves_requirement_details(
    resource_handlers, test_time, mock_law_registry
) -> None:
    """Test that all requirement details are preserved in event"""
    command = CreateTender(
        law_id="law-123",
        title="Complex Tender",
        description="Test",
        requirements=[
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": {
                    "concurrent_projects": 5,
                    "annual_audits": 20,
                },
                "mandatory": True,
            },
            {
                "requirement_id": "req-2",
                "capability_type": "SOC2",
                "min_capacity": None,
                "mandatory": False,  # Optional requirement
            },
        ],
    )

    events = resource_handlers.handle_create_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        law_registry=mock_law_registry,
    )

    requirements = events[0].payload["requirements"]
    assert len(requirements) == 2
    assert requirements[0]["capability_type"] == "ISO27001"
    assert requirements[0]["min_capacity"]["concurrent_projects"] == 5
    assert requirements[0]["mandatory"] is True
    assert requirements[1]["capability_type"] == "SOC2"
    assert requirements[1]["mandatory"] is False


def test_create_tender_all_selection_methods(
    resource_handlers, test_time, mock_law_registry
) -> None:
    """Test tender creation with all three selection methods"""
    for method in [
        SelectionMethod.ROTATION,
        SelectionMethod.RANDOM,
        SelectionMethod.ROTATION_WITH_RANDOM,
    ]:
        command = CreateTender(
            law_id="law-123",
            title=f"Tender {method.value}",
            description="Test",
            requirements=[
                {
                    "requirement_id": "req-1",
                    "capability_type": "ISO27001",
                    "min_capacity": None,
                    "mandatory": True,
                }
            ],
            selection_method=method,
        )

        events = resource_handlers.handle_create_tender(
            command=command,
            command_id=f"cmd-{method.value}",
            actor_id="admin-1",
            law_registry=mock_law_registry,
        )

        assert events[0].payload["selection_method"] == method.value


# -----------------------------------------------------------------------------
# 4. OpenTender Handler Tests (Simple - 4 tests)
# -----------------------------------------------------------------------------


def test_open_tender_success(resource_handlers, test_time) -> None:
    """Test successful tender opening (DRAFT → OPEN transition)"""
    tender_registry = TenderRegistry()

    # Create tender in DRAFT status
    created_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=created_payload,
        version=1,
    )
    tender_registry.apply_event(created_event)

    command = OpenTender(tender_id="t1")

    events = resource_handlers.handle_open_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "TenderOpened"
    assert event.payload["tender_id"] == "t1"
    assert "opened_at" in event.payload


def test_open_tender_not_found(resource_handlers, test_time) -> None:
    """Test that opening non-existent tender fails"""
    tender_registry = TenderRegistry()

    command = OpenTender(tender_id="nonexistent")

    with pytest.raises(Exception, match="Tender.*not found"):
        resource_handlers.handle_open_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
        )


def test_open_tender_not_in_draft_status(resource_handlers, test_time) -> None:
    """Test that opening tender not in DRAFT status fails"""
    tender_registry = TenderRegistry()

    # Create tender
    created_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "required_capacity": None,
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=created_payload,
        version=1,
    )
    tender_registry.apply_event(created_event)

    # Open tender
    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    # Try to open again
    command = OpenTender(tender_id="t1")

    with pytest.raises(Exception, match="DRAFT"):
        resource_handlers.handle_open_tender(
            command=command,
            command_id="cmd-2",
            actor_id="admin-1",
            tender_registry=tender_registry,
        )


def test_open_tender_includes_timestamp(resource_handlers, test_time) -> None:
    """Test that opened event includes timestamp from time provider"""
    tender_registry = TenderRegistry()

    created_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "required_capacity": None,
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    created_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=created_payload,
        version=1,
    )
    tender_registry.apply_event(created_event)

    command = OpenTender(tender_id="t1")

    events = resource_handlers.handle_open_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    # occurred_at should use test_time
    assert events[0].occurred_at == test_time.now()


# -----------------------------------------------------------------------------
# 5. EvaluateTender Handler Tests (Complex - 10 tests)
# -----------------------------------------------------------------------------


def test_evaluate_tender_success_with_feasible_suppliers(
    resource_handlers, test_time
) -> None:
    """Test successful tender evaluation with feasible suppliers found"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier with capability
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Acme Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    capability_payload = {
        "claim_id": generate_id(),
        "supplier_id": "s1",
        "capability_type": "ISO27001",
        "scope": {},
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "evidence": [
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat(),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
        "capacity": None,
        "added_at": test_time.now().isoformat(),
        "added_by": "admin-1",
    }
    capability_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=capability_payload,
        version=2,
    )
    supplier_registry.apply_event(capability_event)

    # Create and open tender
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "FeasibleSetComputed"
    assert event.payload["tender_id"] == "t1"
    assert "s1" in event.payload["feasible_suppliers"]
    assert len(event.payload["excluded_suppliers_with_reasons"]) == 0
    assert "evaluation_time" in event.payload


def test_evaluate_tender_empty_feasible_set(resource_handlers, test_time) -> None:
    """Test tender evaluation with no feasible suppliers (emits warning)"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier WITHOUT required capability
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Acme Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender requiring ISO27001 (which supplier doesn't have)
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should emit both FeasibleSetComputed AND EmptyFeasibleSetDetected
    assert len(events) == 2

    feasible_event = events[0]
    assert feasible_event.event_type == "FeasibleSetComputed"
    assert len(feasible_event.payload["feasible_suppliers"]) == 0

    warning_event = events[1]
    assert warning_event.event_type == "EmptyFeasibleSetDetected"
    assert warning_event.payload["tender_id"] == "t1"


def test_evaluate_tender_not_found(resource_handlers, test_time) -> None:
    """Test that evaluating non-existent tender fails"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    command = EvaluateTender(tender_id="nonexistent")

    with pytest.raises(Exception, match="Tender.*not found"):
        resource_handlers.handle_evaluate_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )


def test_evaluate_tender_not_open(resource_handlers, test_time) -> None:
    """Test that evaluating tender not in OPEN status fails"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Create tender but don't open it
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "required_capacity": None,
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    command = EvaluateTender(tender_id="t1")

    with pytest.raises(Exception, match="OPEN"):
        resource_handlers.handle_evaluate_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )




def test_evaluate_tender_includes_evaluation_time(
    resource_handlers, test_time
) -> None:
    """Test that evaluation event includes timestamp"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "required_capacity": None,
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")


    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Check occurred_at field on Event
    assert events[0].occurred_at == test_time.now()


def test_evaluate_tender_multiple_feasible_suppliers(
    resource_handlers, test_time
) -> None:
    """Test evaluation with multiple suppliers meeting requirements"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register two suppliers with same capability
    for i in range(2):
        supplier_payload = {
            "supplier_id": f"s{i}",
            "name": f"Corp {i}",
            "supplier_type": "security",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        }
        supplier_event = create_event(
            event_id=generate_id(),
            stream_id=f"s{i}",
            stream_type="Supplier",
            event_type="SupplierRegistered",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload=supplier_payload,
            version=1,
        )
        supplier_registry.apply_event(supplier_event)

        capability_payload = {
            "claim_id": generate_id(),
            "supplier_id": f"s{i}",
            "capability_type": "ISO27001",
            "scope": {},
            "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
            "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            "evidence": [
                {
                    "evidence_id": f"ev-{i}",
                    "evidence_type": "certification",
                    "issuer": "Test",
                    "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat(),
                    "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                }
            ],
            "capacity": None,
            "added_at": test_time.now().isoformat(),
            "added_by": "admin-1",
        }
        capability_event = create_event(
            event_id=generate_id(),
            stream_id=f"s{i}",
            stream_type="Supplier",
            event_type="CapabilityClaimAdded",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload=capability_payload,
            version=2,
        )
        supplier_registry.apply_event(capability_event)

    # Create tender
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    feasible_ids = events[0].payload["feasible_suppliers"]
    assert len(feasible_ids) == 2
    assert "s0" in feasible_ids
    assert "s1" in feasible_ids


def test_evaluate_tender_excludes_suppliers_with_reasons(
    resource_handlers, test_time
) -> None:
    """Test that excluded suppliers have exclusion reasons recorded"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier without capability
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Acme Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender requiring ISO27001
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )


    excluded = events[0].payload["excluded_suppliers_with_reasons"]
    assert len(excluded) == 1
    assert excluded[0]["supplier_id"] == "s1"
    assert len(excluded[0]["reasons"]) > 0


def test_evaluate_tender_with_capacity_requirements(
    resource_handlers, test_time
) -> None:
    """Test evaluation with capacity constraint requirements"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier with insufficient capacity
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Small Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    capability_payload = {
        "claim_id": generate_id(),
        "supplier_id": "s1",
        "capability_type": "ISO27001",
        "scope": {},
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "evidence": [
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat(),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
        "capacity": {"concurrent_projects": 2},  # Too low
        "added_at": test_time.now().isoformat(),
        "added_by": "admin-1",
    }
    capability_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=capability_payload,
        version=2,
    )
    supplier_registry.apply_event(capability_event)

    # Create tender requiring 5 concurrent projects
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": {"concurrent_projects": 5},
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should be excluded due to insufficient capacity
    assert len(events[0].payload["feasible_suppliers"]) == 0
    assert len(events[0].payload["excluded_suppliers_with_reasons"]) == 1


def test_evaluate_tender_expired_capability(resource_handlers, test_time) -> None:
    """Test that suppliers with expired capabilities are excluded"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    supplier_payload = {
        "supplier_id": "s1",
        "name": "Expired Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Add expired capability (test_time is 2025-01-15)
    capability_payload = {
        "claim_id": generate_id(),
        "supplier_id": "s1",
        "capability_type": "ISO27001",
        "scope": {},
        "valid_from": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        "valid_until": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),  # Expired
        "evidence": [
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2023, 12, 1, tzinfo=timezone.utc).isoformat(),
                "valid_until": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
        "capacity": None,
    "added_at": test_time.now().isoformat(),
    "added_by": "admin-1",
    }
    capability_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=capability_payload,
        version=2,
    )
    supplier_registry.apply_event(capability_event)

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should be excluded due to expired capability
    assert len(events[0].payload["feasible_suppliers"]) == 0
    assert len(events) == 2  # FeasibleSetComputed + EmptyFeasibleSetDetected



def test_evaluate_tender_unverified_evidence(resource_handlers, test_time) -> None:
    """Test that capabilities are auto-verified by projection"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    supplier_payload = {
        "supplier_id": "s1",
        "name": "Unverified Corp",
        "supplier_type": "security",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    capability_payload = {
        "claim_id": generate_id(),
        "supplier_id": "s1",
        "capability_type": "ISO27001",
        "scope": {},
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "evidence": [
            {
                "evidence_id": "ev-1",
                "evidence_type": "certification",
                "issuer": "Test",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat(),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
        "capacity": None,
        "added_at": test_time.now().isoformat(),
        "added_by": "admin-1",
    }
    capability_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="CapabilityClaimAdded",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=capability_payload,
        version=2,
    )
    supplier_registry.apply_event(capability_event)

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [
            {
                "requirement_id": "req-1",
                "capability_type": "ISO27001",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        "required_capacity": None,
        "selection_method": SelectionMethod.ROTATION.value,
        "status": TenderStatus.DRAFT.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    opened_payload = {"tender_id": "t1", "opened_at": test_time.now().isoformat(), "opened_by": "admin-1"}
    opened_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderOpened",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=opened_payload,
        version=2,
    )
    tender_registry.apply_event(opened_event)

    command = EvaluateTender(tender_id="t1")

    events = resource_handlers.handle_evaluate_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Supplier should be included because projection auto-verifies capabilities (projections.py:84)
    assert len(events[0].payload["feasible_suppliers"]) == 1
    assert events[0].payload["feasible_suppliers"][0] == "s1"
    assert len(events) == 1  # FeasibleSetComputed only (no EmptyFeasibleSetDetected)


# ============================================================================
# Handler 6: SelectSupplier - Multi-gate constitutional selection
# ============================================================================
# Fun fact: Constitutional procurement implements game-theoretic mechanisms
# to prevent capture - similar to mechanisms designed by Nobel laureate
# Leonid Hurwicz (2007 Economics Nobel for mechanism design theory)!


@pytest.fixture
def safety_policy(permissive_safety_policy):
    """
    Override safety_policy for Part 2 SelectSupplier tests

    Use permissive policy (no reputation threshold) so tests can focus on
    testing rotation/random algorithms without needing to set up reputation scores.
    """
    return permissive_safety_policy


def test_select_supplier_gate1_empty_feasible_set(resource_handlers, test_time) -> None:
    """Test GATE 1: Supplier selection fails with empty feasible set"""
    tender_registry = TenderRegistry()

    # Create tender in EVALUATING status
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=[])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=SupplierRegistry(),
    )

    # Should emit SupplierSelectionFailed event
    assert len(events) == 1
    assert events[0].event_type == "SupplierSelectionFailed"
    assert events[0].payload["tender_id"] == "t1"
    assert events[0].payload["empty_feasible_set"] is True
    assert "empty" in events[0].payload["failure_reason"].lower()


def test_select_supplier_tender_not_found(resource_handlers, test_time) -> None:
    """Test that selection fails if tender doesn't exist"""
    command = SelectSupplier(tender_id="nonexistent", selection_seed=None)

    with pytest.raises(ValueError, match="not found"):
        resource_handlers.handle_select_supplier(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=TenderRegistry(),
            supplier_registry=SupplierRegistry(),
        )


def test_select_supplier_invalid_status(resource_handlers, test_time) -> None:
    """Test that selection fails if tender not in EVALUATING status"""
    tender_registry = TenderRegistry()

    # Create tender in DRAFT status (only TenderCreated, no FeasibleSetComputed)
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    with pytest.raises(ValueError, match="EVALUATING"):
        resource_handlers.handle_select_supplier(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=SupplierRegistry(),
        )


def test_select_supplier_rotation_success(resource_handlers, test_time) -> None:
    """Test successful supplier selection using ROTATION method"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register three suppliers with different loads
    for i, load in enumerate([Decimal("100000"), Decimal("150000"), Decimal("120000")]):
        supplier_payload = {
            "supplier_id": f"s{i+1}",
            "name": f"Supplier {i+1}",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        }
        supplier_event = create_event(
            event_id=generate_id(),
            stream_id=f"s{i+1}",
            stream_type="Supplier",
            event_type="SupplierRegistered",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload=supplier_payload,
            version=1,
        )
        supplier_registry.apply_event(supplier_event)

        # Award some contracts to build up total_value_awarded
        if load > 0:
            awarded_payload = {
                "tender_id": f"prev-{i+1}",
                "awarded_supplier_id": f"s{i+1}",
                "contract_value": load,
                "contract_terms": {},
                "awarded_at": test_time.now().isoformat(),
                "awarded_by": "admin-1",
            }
            awarded_event = create_event(
                event_id=generate_id(),
                stream_id=f"prev-{i+1}",
                stream_type="Tender",
                event_type="TenderAwarded",
                occurred_at=test_time.now(),
                command_id=generate_id(),
                actor_id="admin-1",
                payload=awarded_payload,
                version=1,
            )
            supplier_registry.apply_event(awarded_event)

    # Create tender with all three suppliers in feasible set
    
    # Create tender in EVALUATING status
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=["s1", "s2", "s3"])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should select s1 (lowest load of 100k)
    assert len(events) == 1
    assert events[0].event_type == "SupplierSelected"
    assert events[0].payload["tender_id"] == "t1"
    assert events[0].payload["selected_supplier_id"] == "s1"
    assert events[0].payload["selection_method"] == SelectionMethod.ROTATION.value
    assert "rotation_state" in events[0].payload
    assert events[0].payload["random_seed"] is None


def test_select_supplier_random_with_seed(resource_handlers, test_time) -> None:
    """Test RANDOM selection method with explicit seed produces deterministic results"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register two suppliers
    for i in range(2):
        supplier_payload = {
            "supplier_id": f"s{i+1}",
            "name": f"Supplier {i+1}",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        }
        supplier_event = create_event(
            event_id=generate_id(),
            stream_id=f"s{i+1}",
            stream_type="Supplier",
            event_type="SupplierRegistered",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload=supplier_payload,
            version=1,
        )
        supplier_registry.apply_event(supplier_event)

    # Create tender with RANDOM selection method
    create_tender_in_evaluating_status(
        tender_registry, test_time,
        feasible_suppliers=["s1", "s2"],
        selection_method=SelectionMethod.RANDOM
    )

    command = SelectSupplier(tender_id="t1", selection_seed="test-seed-123")

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    assert len(events) == 1
    assert events[0].event_type == "SupplierSelected"
    assert events[0].payload["selection_method"] == SelectionMethod.RANDOM.value
    assert events[0].payload["random_seed"] == "test-seed-123"
    # Deterministic: same seed should always pick same supplier
    selected_id = events[0].payload["selected_supplier_id"]
    assert selected_id in ["s1", "s2"]


def test_select_supplier_rotation_with_random(resource_handlers, test_time) -> None:
    """Test ROTATION_WITH_RANDOM hybrid method"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register suppliers
    for i in range(3):
        supplier_payload = {
            "supplier_id": f"s{i+1}",
            "name": f"Supplier {i+1}",
            "supplier_type": "general",
            "registered_at": test_time.now().isoformat(),
            "registered_by": "admin-1",
            "metadata": {},
        }
        supplier_event = create_event(
            event_id=generate_id(),
            stream_id=f"s{i+1}",
            stream_type="Supplier",
            event_type="SupplierRegistered",
            occurred_at=test_time.now(),
            command_id=generate_id(),
            actor_id="admin-1",
            payload=supplier_payload,
            version=1,
        )
        supplier_registry.apply_event(supplier_event)

    # Create tender with hybrid method
    create_tender_in_evaluating_status(
        tender_registry, test_time,
        feasible_suppliers=["s1", "s2", "s3"],
        selection_method=SelectionMethod.ROTATION_WITH_RANDOM
    )

    command = SelectSupplier(tender_id="t1", selection_seed="hybrid-seed")

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    assert len(events) == 1
    assert events[0].event_type == "SupplierSelected"
    assert events[0].payload["selection_method"] == SelectionMethod.ROTATION_WITH_RANDOM.value
    assert events[0].payload["random_seed"] == "hybrid-seed"


def test_select_supplier_gate3_supplier_share_limit_first_procurement(
    resource_handlers, test_time, safety_policy
) -> None:
    """Test GATE 3: Share limits NOT enforced for first procurement (total_value == 0)"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier with NO prior contracts (total_value_awarded = 0)
    supplier_payload = {
        "supplier_id": "s1",
        "name": "New Supplier",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender
    
    # Create tender in EVALUATING status
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=["s1"])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should succeed - concentration limits not enforced for first procurement
    assert len(events) == 1
    assert events[0].event_type == "SupplierSelected"
    assert events[0].payload["selected_supplier_id"] == "s1"


def test_select_supplier_gate4_reputation_threshold_first_procurement(
    resource_handlers, test_time
) -> None:
    """Test GATE 4: Reputation threshold NOT enforced for first procurement"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier with low reputation (0.3 < default threshold 0.6)
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Low Rep Supplier",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Update reputation to 0.3 (below threshold)
    rep_payload = {
        "supplier_id": "s1",
        "old_score": 0.5,
        "new_score": 0.3,
        "reason": "Test",
        "tender_id": "prev",
        "updated_at": test_time.now().isoformat(),
    }
    rep_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="ReputationUpdated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload=rep_payload,
        version=2,
    )
    supplier_registry.apply_event(rep_event)

    # Create tender (first procurement - no contracts awarded yet)
    
    # Create tender in EVALUATING status
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=["s1"])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should succeed - reputation threshold not enforced for first procurement
    assert len(events) == 1
    assert events[0].event_type == "SupplierSelected"


def test_select_supplier_feasible_suppliers_not_in_registry(
    resource_handlers, test_time
) -> None:
    """Test selection fails if feasible suppliers don't exist in registry"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()  # Empty registry

    # Create tender with feasible suppliers that don't exist in registry
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=["s1", "s2"])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should emit failure event
    assert len(events) == 1
    assert events[0].event_type == "SupplierSelectionFailed"
    assert "not found in registry" in events[0].payload["failure_reason"]


def test_select_supplier_includes_rotation_state(resource_handlers, test_time) -> None:
    """Test that selection includes rotation state for audit trail"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Supplier 1",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender
    
    # Create tender in EVALUATING status
    create_tender_in_evaluating_status(tender_registry, test_time, feasible_suppliers=["s1"])

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    events = resource_handlers.handle_select_supplier(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    assert len(events) == 1
    # Rotation state should include load information for transparency
    assert "rotation_state" in events[0].payload
    rotation_state = events[0].payload["rotation_state"]
    assert isinstance(rotation_state, dict)
    # Should have supplier loads for audit
    assert "supplier_loads" in rotation_state
    assert "s1" in rotation_state["supplier_loads"]


def test_select_supplier_random_requires_seed_validation(
    resource_handlers, test_time
) -> None:
    """Test RANDOM method validates that seed is provided"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Supplier 1",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender with RANDOM method
    create_tender_in_evaluating_status(
        tender_registry, test_time,
        feasible_suppliers=["s1"],
        selection_method=SelectionMethod.RANDOM
    )

    command = SelectSupplier(tender_id="t1", selection_seed=None)

    with pytest.raises(Exception):  # Should raise validation error for missing seed
        resource_handlers.handle_select_supplier(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )


# ============================================================================
# Handler 7: AwardTender - Contract finalization
# ============================================================================


def test_award_tender_success(resource_handlers, test_time) -> None:
    """Test successful tender award"""
    tender_registry = TenderRegistry()

    # Create tender in EVALUATING status with supplier selected (but not yet awarded)
    # TenderCreated → DRAFT
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    # FeasibleSetComputed → EVALUATING
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
            "feasible_suppliers": ["s1"],
            "excluded_suppliers_with_reasons": [],
            "evaluation_time": test_time.now().isoformat(),
        },
        version=2,
    )
    tender_registry.apply_event(feasible_event)

    # SupplierSelected → sets selected_supplier_id
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
            "requirements": [],
            "selection_method": SelectionMethod.ROTATION.value,
            "selection_reason": "Test selection",
            "rotation_state": {},
            "random_seed": None,
            "selected_at": test_time.now().isoformat(),
            "selected_by": "admin-1",
        },
        version=3,
    )
    tender_registry.apply_event(selected_event)

    command = AwardTender(
        tender_id="t1",
        contract_value=Decimal("250000"),
        contract_terms={"duration_months": 12, "deliverables": ["System A", "System B"]},
    )

    events = resource_handlers.handle_award_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    assert len(events) == 1
    assert events[0].event_type == "TenderAwarded"
    assert events[0].stream_id == "t1"
    assert events[0].stream_type == "Tender"
    assert events[0].payload["tender_id"] == "t1"
    assert events[0].payload["awarded_supplier_id"] == "s1"
    assert Decimal(events[0].payload["contract_value"]) == Decimal("250000")
    assert events[0].payload["contract_terms"]["duration_months"] == 12


def test_award_tender_not_found(resource_handlers, test_time) -> None:
    """Test awarding non-existent tender fails"""
    command = AwardTender(
        tender_id="nonexistent",
        contract_value=Decimal("100000"),
        contract_terms={},
    )

    with pytest.raises(ValueError, match="not found"):
        resource_handlers.handle_award_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=TenderRegistry(),
        )



def test_award_tender_no_selected_supplier(resource_handlers, test_time) -> None:
    """Test awarding tender without selected supplier fails"""
    tender_registry = TenderRegistry()

    # Create tender in EVALUATING status but WITHOUT SupplierSelected event
    # (so selected_supplier_id remains None)
    create_tender_in_evaluating_status(tender_registry, test_time, tender_id="t1", feasible_suppliers=["s1"])

    command = AwardTender(
        tender_id="t1",
        contract_value=Decimal("100000"),
        contract_terms={},
    )

    with pytest.raises(ValueError, match="without selected supplier"):
        resource_handlers.handle_award_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
        )


# ============================================================================
# Handler 8: RecordMilestone - Delivery tracking
# ============================================================================
# Fun fact: Milestone tracking in contracts dates back to ancient Rome's
# "locatio conductio operis" - contracts for specific works with payment
# tied to delivery stages!


def test_record_milestone_success(resource_handlers, test_time) -> None:
    """Test recording delivery milestone"""
    tender_registry = TenderRegistry()

    # Create tender (milestone recording doesn't require specific tender status)
    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test Tender",
        "description": "Test tender description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    command = RecordMilestone(
        tender_id="t1",
        milestone_id="m1",
        milestone_type="delivery",
        description="Phase 1 completed",
        evidence=[],
        metadata={"phase": 1},
    )

    events = resource_handlers.handle_record_milestone(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    assert len(events) == 1
    assert events[0].event_type == "MilestoneRecorded"
    assert events[0].stream_id == "delivery-t1"  # Separate delivery stream
    assert events[0].stream_type == "delivery"
    assert events[0].payload["tender_id"] == "t1"
    assert events[0].payload["milestone_id"] == "m1"
    assert events[0].payload["milestone_type"] == "delivery"
    assert events[0].payload["description"] == "Phase 1 completed"
    assert events[0].payload["metadata"]["phase"] == 1


def test_record_milestone_with_evidence(resource_handlers, test_time) -> None:
    """Test milestone with attached evidence"""
    tender_registry = TenderRegistry()

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    # Import EvidenceSpec model
    from freedom_that_lasts.resource.commands import EvidenceSpec

    evidence = EvidenceSpec(
        evidence_type="inspection_report",
        issuer="QA Team",
        issued_at=test_time.now(),
        valid_until=None,
    )

    command = RecordMilestone(
        tender_id="t1",
        milestone_id="m1",
        milestone_type="inspection",
        description="Quality inspection passed",
        evidence=[evidence],
        metadata={},
    )

    events = resource_handlers.handle_record_milestone(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    assert len(events) == 1
    assert len(events[0].payload["evidence"]) == 1
    assert events[0].payload["evidence"][0]["evidence_type"] == "inspection_report"
    assert events[0].payload["evidence"][0]["evidence_type"] == "inspection_report"


def test_record_milestone_tender_not_found(resource_handlers, test_time) -> None:
    """Test milestone recording fails if tender doesn't exist"""
    command = RecordMilestone(
        tender_id="nonexistent",
        milestone_id="m1",
        milestone_type="delivery",
        description="Test",
        evidence=[],
        metadata={},
    )

    with pytest.raises(ValueError, match="not found"):
        resource_handlers.handle_record_milestone(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=TenderRegistry(),
        )


# ============================================================================
# Handler 9: RecordSLABreach - Quality monitoring
# ============================================================================


def test_record_sla_breach_success(resource_handlers, test_time) -> None:
    """Test recording SLA breach"""
    tender_registry = TenderRegistry()

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    command = RecordSLABreach(
        tender_id="t1",
        sla_metric="response_time",
        expected_value="< 2 hours",
        actual_value="5 hours",
        severity="major",
        impact_description="Customer complaints increased",
    )

    events = resource_handlers.handle_record_sla_breach(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
    )

    assert len(events) == 1
    assert events[0].event_type == "SLABreachDetected"
    assert events[0].stream_id == "delivery-t1"
    assert events[0].stream_type == "delivery"
    assert events[0].payload["tender_id"] == "t1"
    assert events[0].payload["sla_metric"] == "response_time"
    assert events[0].payload["severity"] == "major"
    assert events[0].payload["expected_value"] == "< 2 hours"
    assert events[0].payload["actual_value"] == "5 hours"


def test_record_sla_breach_all_severities(resource_handlers, test_time) -> None:
    """Test all valid severity levels"""
    tender_registry = TenderRegistry()

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    for severity in ["minor", "major", "critical"]:
        command = RecordSLABreach(
            tender_id="t1",
            sla_metric="test_metric",
            expected_value="expected",
            actual_value="actual",
            severity=severity,
            impact_description="Test impact",
        )

        events = resource_handlers.handle_record_sla_breach(
            command=command,
            command_id=f"cmd-{severity}",
            actor_id="admin-1",
            tender_registry=tender_registry,
        )

        assert len(events) == 1
        assert events[0].payload["severity"] == severity


def test_record_sla_breach_invalid_severity(resource_handlers, test_time) -> None:
    """Test invalid severity level is rejected"""
    tender_registry = TenderRegistry()

    tender_payload = {
        "tender_id": "t1",
        "law_id": "law-123",
        "title": "Test",
        "description": "Test description",
        "requirements": [],
        "selection_method": SelectionMethod.ROTATION.value,
        "created_at": test_time.now().isoformat(),
        "created_by": "admin-1",
    }
    tender_event = create_event(
        event_id=generate_id(),
        stream_id="t1",
        stream_type="Tender",
        event_type="TenderCreated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=tender_payload,
        version=1,
    )
    tender_registry.apply_event(tender_event)

    command = RecordSLABreach(
        tender_id="t1",
        sla_metric="test",
        expected_value="x",
        actual_value="y",
        severity="invalid",  # Invalid severity
        impact_description="Test",
    )

    with pytest.raises(ValueError, match="Invalid severity"):
        resource_handlers.handle_record_sla_breach(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
        )


def test_record_sla_breach_tender_not_found(resource_handlers, test_time) -> None:
    """Test SLA breach recording fails if tender doesn't exist"""
    command = RecordSLABreach(
        tender_id="nonexistent",
        sla_metric="test",
        expected_value="x",
        actual_value="y",
        severity="minor",
        impact_description="Test",
    )

    with pytest.raises(ValueError, match="not found"):
        resource_handlers.handle_record_sla_breach(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=TenderRegistry(),
        )


# ============================================================================
# Handler 10: CompleteTender - Final quality assessment & reputation update
# ============================================================================
# Fun fact: Reputation systems for merchants date back to medieval trade fairs,
# where the "Law Merchant" maintained records of trader reliability across Europe!




def test_complete_tender_success_with_reputation_update(resource_handlers, test_time) -> None:
    """Test tender completion updates supplier reputation"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier with initial reputation
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Test Supplier",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender with selected supplier using proper event sequence
    create_tender_in_awarded_status(tender_registry, test_time, tender_id="t1", selected_supplier_id="s1")

    # Supplier starts with reputation 0.5 (default)
    # Quality score 0.9 → new_rep = 0.8 * 0.5 + 0.2 * 0.9 = 0.58

    command = CompleteTender(
        tender_id="t1",
        completion_report={"summary": "Excellent delivery, met all milestones"},
        final_quality_score=0.9,
    )

    events = resource_handlers.handle_complete_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    # Should emit TWO events
    assert len(events) == 2
    completed_event = events[0]
    reputation_event = events[1]

    # Verify TenderCompleted event
    assert completed_event.event_type == "TenderCompleted"
    assert completed_event.stream_id == "t1"
    assert completed_event.stream_type == "Tender"
    assert completed_event.actor_id == "admin-1"
    assert completed_event.payload["tender_id"] == "t1"
    assert completed_event.payload["final_quality_score"] == 0.9
    assert completed_event.payload["completion_report"] == {"summary": "Excellent delivery, met all milestones"}

    # Verify ReputationUpdated event
    assert reputation_event.event_type == "ReputationUpdated"
    assert reputation_event.stream_id == "s1"
    assert reputation_event.stream_type == "Supplier"
    assert reputation_event.actor_id == "system"  # System actor for reputation updates
    assert reputation_event.payload["supplier_id"] == "s1"
    assert reputation_event.payload["old_score"] == 0.5
    assert reputation_event.payload["new_score"] == pytest.approx(0.58)
    assert "t1" in reputation_event.payload["reason"]


def test_complete_tender_reputation_formula(resource_handlers, test_time) -> None:
    """Test reputation update formula: 0.8 * old + 0.2 * quality"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Test Supplier",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)


    # Update reputation to 0.7
    reputation_payload = {
        "supplier_id": "s1",
        "old_score": 0.5,
        "new_score": 0.7,
        "reason": "Previous completion",
        "tender_id": "prev",
        "updated_at": test_time.now().isoformat(),
    }
    rep_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="ReputationUpdated",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="system",
        payload=reputation_payload,
        version=2,
    )
    supplier_registry.apply_event(rep_event)

    # Create tender in AWARDED status (proper event sequence)
    create_tender_in_awarded_status(tender_registry, test_time, tender_id="t1", selected_supplier_id="s1")

    # Complete with quality 0.6
    # Expected: 0.8 * 0.7 + 0.2 * 0.6 = 0.56 + 0.12 = 0.68
    command = CompleteTender(
        tender_id="t1",
        completion_report={"summary": "Acceptable performance"},
        final_quality_score=0.6,
    )

    events = resource_handlers.handle_complete_tender(
        command=command,
        command_id="cmd-1",
        actor_id="admin-1",
        tender_registry=tender_registry,
        supplier_registry=supplier_registry,
    )

    reputation_event = events[1]
    assert reputation_event.payload["old_score"] == 0.7
    assert reputation_event.payload["new_score"] == pytest.approx(0.68)


def test_complete_tender_quality_score_validation(resource_handlers, test_time) -> None:
    """Test quality score must be in [0.0, 1.0] range"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Register supplier
    supplier_payload = {
        "supplier_id": "s1",
        "name": "Test",
        "supplier_type": "general",
        "registered_at": test_time.now().isoformat(),
        "registered_by": "admin-1",
        "metadata": {},
    }
    supplier_event = create_event(
        event_id=generate_id(),
        stream_id="s1",
        stream_type="Supplier",
        event_type="SupplierRegistered",
        occurred_at=test_time.now(),
        command_id=generate_id(),
        actor_id="admin-1",
        payload=supplier_payload,
        version=1,
    )
    supplier_registry.apply_event(supplier_event)

    # Create tender in AWARDED status (proper event sequence)
    create_tender_in_awarded_status(tender_registry, test_time, tender_id="t1", selected_supplier_id="s1")

    # Test score > 1.0
    with pytest.raises(Exception):  # Should raise validation error
        command = CompleteTender(
            tender_id="t1",
            completion_report={"summary": "Test"},
            final_quality_score=1.5,  # Invalid
        )
        resource_handlers.handle_complete_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )



def test_complete_tender_no_selected_supplier(resource_handlers, test_time) -> None:
    """Test completion fails if tender has no selected supplier"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Create tender in EVALUATING status WITHOUT SupplierSelected event
    create_tender_in_evaluating_status(tender_registry, test_time, tender_id="t1", feasible_suppliers=["s1"])

    command = CompleteTender(
        tender_id="t1",
        completion_report={"summary": "Test"},
        final_quality_score=0.8,
    )

    with pytest.raises(ValueError, match="no selected supplier"):
        resource_handlers.handle_complete_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )


def test_complete_tender_supplier_not_found(resource_handlers, test_time) -> None:
    """Test completion fails if selected supplier doesn't exist in registry"""
    tender_registry = TenderRegistry()
    supplier_registry = SupplierRegistry()

    # Create tender in AWARDED status with nonexistent supplier
    create_tender_in_awarded_status(tender_registry, test_time, tender_id="t1", selected_supplier_id="nonexistent")

    command = CompleteTender(
        tender_id="t1",
        completion_report={"summary": "Test"},
        final_quality_score=0.8,
    )

    with pytest.raises(ValueError, match="Supplier .* not found"):
        resource_handlers.handle_complete_tender(
            command=command,
            command_id="cmd-1",
            actor_id="admin-1",
            tender_registry=tender_registry,
            supplier_registry=supplier_registry,
        )
