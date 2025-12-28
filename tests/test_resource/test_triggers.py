"""
Tests for Resource Triggers

Tests automatic procurement health monitoring triggers that detect:
- Empty feasible sets (requirements too strict)
- Supplier concentration violations (anti-capture safeguards)

Fun fact: The trigger pattern comes from database systems (1970s IBM),
but we're using it to trigger constitutional democracy safeguards!
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.resource.models import TenderStatus
from freedom_that_lasts.resource.triggers import (
    evaluate_empty_feasible_set_trigger,
    evaluate_supplier_concentration_trigger,
    evaluate_all_procurement_triggers,
)


# =============================================================================
# Empty Feasible Set Trigger Tests
# =============================================================================


def test_empty_feasible_set_no_evaluating_tenders():
    """Test no events when no tenders are evaluating"""
    tenders = []
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert events == []


def test_empty_feasible_set_tender_has_suppliers():
    """Test no events when feasible set is non-empty"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-123",
            "feasible_suppliers": ["s1", "s2"],
            "requirements": [{"capability_type": "ISO27001"}],
        }
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert events == []


def test_empty_feasible_set_emits_event():
    """Test EmptyFeasibleSetDetected event when feasible set is empty"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-123",
            "feasible_suppliers": [],
            "requirements": [{"capability_type": "ISO27001"}],
            "required_capacity": {"concurrent_projects": 5},
            "excluded_suppliers_with_reasons": [
                {"supplier_id": "s1", "reason": "Missing capability"}
            ],
        }
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert len(events) == 1
    event = events[0]

    # Event metadata
    assert event.stream_id == "t1"
    assert event.stream_type == "Tender"
    assert event.event_type == "EmptyFeasibleSetDetected"
    assert event.actor_id == "system"
    assert event.command_id == "trigger"
    assert event.occurred_at == now
    assert event.version == 1

    # Event payload
    payload = event.payload
    assert payload["tender_id"] == "t1"
    assert payload["law_id"] == "law-123"
    assert payload["detected_at"] == now.isoformat().replace("+00:00", "Z")
    assert payload["action_required"] == "Review requirements or build supplier capacity"

    # Requirements summary
    summary = payload["requirements_summary"]
    assert summary["requirements"] == [{"capability_type": "ISO27001"}]
    assert summary["required_capacity"] == {"concurrent_projects": 5}
    assert summary["excluded_count"] == 1


def test_empty_feasible_set_multiple_tenders_mixed():
    """Test only empty tenders trigger events"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-1",
            "feasible_suppliers": ["s1"],  # Has suppliers
            "requirements": [],
        },
        {
            "tender_id": "t2",
            "law_id": "law-2",
            "feasible_suppliers": [],  # Empty!
            "requirements": [{"capability_type": "ISO27001"}],
        },
        {
            "tender_id": "t3",
            "law_id": "law-3",
            "feasible_suppliers": [],  # Empty!
            "requirements": [{"capability_type": "PCI-DSS"}],
        },
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert len(events) == 2
    tender_ids = {e.payload["tender_id"] for e in events}
    assert tender_ids == {"t2", "t3"}


def test_empty_feasible_set_missing_field_treated_as_empty():
    """Test tender without feasible_suppliers field is treated as empty"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-123",
            # Missing feasible_suppliers field
            "requirements": [],
        }
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert len(events) == 1
    assert events[0].payload["tender_id"] == "t1"


def test_empty_feasible_set_handles_missing_optional_fields():
    """Test trigger handles tenders missing optional fields gracefully"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-123",
            "feasible_suppliers": [],
            # Missing requirements, required_capacity, excluded_suppliers_with_reasons
        }
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert len(events) == 1
    payload = events[0].payload

    # Should use defaults for missing fields
    summary = payload["requirements_summary"]
    assert summary["requirements"] == []
    assert summary["required_capacity"] is None
    assert summary["excluded_count"] == 0


def test_empty_feasible_set_none_treated_as_empty():
    """Test feasible_suppliers=None is treated as empty"""
    tenders = [
        {
            "tender_id": "t1",
            "law_id": "law-123",
            "feasible_suppliers": None,  # Explicitly None
            "requirements": [],
        }
    ]
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_empty_feasible_set_trigger(tenders, now)

    assert len(events) == 1


# =============================================================================
# Supplier Concentration Trigger Tests
# =============================================================================


def test_concentration_no_suppliers():
    """Test no events when no suppliers exist"""
    supplier_registry = {"suppliers": {}}
    tender_registry = {}
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert events == []


def test_concentration_empty_supplier_list():
    """Test no events when supplier registry is empty"""
    supplier_registry = {}  # Missing 'suppliers' key
    tender_registry = {}
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert events == []


def test_concentration_single_supplier_exceeds_halt():
    """Test single supplier (100% share) triggers halt"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("1000000"),
            }
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.35,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    event = events[0]

    # Event metadata
    assert event.stream_id == "s1"
    assert event.stream_type == "Supplier"
    assert event.event_type == "SupplierConcentrationHalt"
    assert event.actor_id == "system"
    assert event.command_id == "trigger"
    assert event.version == 1

    # Event payload
    payload = event.payload
    assert payload["halted_supplier_id"] == "s1"
    assert payload["supplier_share"] == 1.0  # 100% share
    assert payload["critical_threshold_exceeded"] == 0.35
    assert payload["total_procurement_value"] == "1000000"
    assert payload["gini_coefficient"] >= 0.0  # Single supplier has Gini = 0


def test_concentration_balanced_suppliers_no_events():
    """Test balanced suppliers under threshold emit no events"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("100000"),
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("100000"),
            },
            "s3": {
                "supplier_id": "s3",
                "total_value_awarded": Decimal("100000"),
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.40,  # Each has 33%, under 40%
        supplier_share_halt_threshold=0.50,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert events == []


def test_concentration_exactly_at_warn_threshold_no_event():
    """Test supplier exactly at warn threshold does not trigger (only >threshold)"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("200000"),  # Exactly 20%
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("800000"),  # 80%
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.80,  # Exactly at threshold
        supplier_share_halt_threshold=0.90,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    # Should not trigger because share == threshold, not >threshold
    assert events == []


def test_concentration_just_over_warn_threshold():
    """Test supplier just over warn threshold triggers warning"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("210000"),  # 21% (over 20%)
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("790000"),  # 79%
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.90,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    event = events[0]

    # Should emit warning, not halt
    assert event.event_type == "SupplierConcentrationWarning"
    payload = event.payload
    assert payload["top_supplier_id"] == "s2"  # s2 has highest share (79%)
    assert payload["top_supplier_share"] == 0.79
    assert payload["threshold_exceeded"] == 0.20


def test_concentration_exactly_at_halt_threshold_no_halt():
    """Test supplier exactly at halt threshold triggers warning but not halt"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("350000"),  # 35%
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("650000"),  # 65% (exactly at halt)
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.65,  # Exactly at threshold
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    # Should emit warning (share > 0.20 warn threshold)
    # But not halt (share == 0.65, not > 0.65)
    assert len(events) == 1
    assert events[0].event_type == "SupplierConcentrationWarning"


def test_concentration_just_over_halt_threshold():
    """Test supplier just over halt threshold triggers halt"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("360000"),  # 36% (over 35%)
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("640000"),  # 64%
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.35,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    event = events[0]

    # Should emit halt, not warning (halt takes precedence)
    assert event.event_type == "SupplierConcentrationHalt"
    payload = event.payload
    assert payload["halted_supplier_id"] == "s2"  # s2 has highest share (64%)
    assert payload["supplier_share"] == 0.64
    assert payload["critical_threshold_exceeded"] == 0.35


def test_concentration_halt_takes_precedence_over_warning():
    """Test halt event emitted instead of warning when share > halt threshold"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("400000"),  # 40% (over halt)
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("600000"),  # 60%
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,  # Would trigger warning
        supplier_share_halt_threshold=0.35,  # But halt takes precedence
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    assert events[0].event_type == "SupplierConcentrationHalt"  # Not warning


def test_concentration_warning_payload_structure():
    """Test SupplierConcentrationWarning event has correct payload structure"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("250000"),  # 25% (over 20% warn)
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("750000"),  # 75%
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.90,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    payload = events[0].payload

    # Validate all required fields
    assert payload["detected_at"] == now.isoformat().replace("+00:00", "Z")
    assert payload["total_procurement_value"] == "1000000"
    assert "supplier_shares" in payload
    assert payload["supplier_shares"]["s1"] == 0.25
    assert payload["supplier_shares"]["s2"] == 0.75
    assert "gini_coefficient" in payload
    assert payload["gini_coefficient"] >= 0.0
    assert payload["top_supplier_id"] == "s2"
    assert payload["top_supplier_share"] == 0.75
    assert payload["threshold_exceeded"] == 0.20


def test_concentration_halt_payload_structure():
    """Test SupplierConcentrationHalt event has correct payload structure"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("100000"),  # 10%
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("900000"),  # 90% (over 35% halt)
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.35,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    payload = events[0].payload

    # Validate all required fields
    assert payload["detected_at"] == now.isoformat().replace("+00:00", "Z")
    assert payload["total_procurement_value"] == "1000000"
    assert "supplier_shares" in payload
    assert payload["gini_coefficient"] >= 0.0
    assert payload["halted_supplier_id"] == "s2"
    assert payload["supplier_share"] == 0.90
    assert payload["critical_threshold_exceeded"] == 0.35


def test_concentration_gini_coefficient_computed():
    """Test Gini coefficient is computed and included in events"""
    supplier_registry = {
        "suppliers": {
            "s1": {
                "supplier_id": "s1",
                "total_value_awarded": Decimal("100000"),
            },
            "s2": {
                "supplier_id": "s2",
                "total_value_awarded": Decimal("900000"),
            },
        }
    }
    tender_registry = {}
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.35,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_supplier_concentration_trigger(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    gini = events[0].payload["gini_coefficient"]

    # High inequality (90/10 split) should have Gini > 0.3
    # (Gini coefficient for 90/10 split is 0.4)
    assert gini > 0.3
    assert gini <= 1.0


# =============================================================================
# Integration: evaluate_all_procurement_triggers
# =============================================================================


def test_all_triggers_no_issues():
    """Test no events when no issues detected"""
    supplier_registry = {
        "suppliers": {
            "s1": {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
            "s2": {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},
        }
    }
    tender_registry = {
        "tenders": {
            "t1": {
                "tender_id": "t1",
                "status": TenderStatus.EVALUATING,
                "feasible_suppliers": ["s1", "s2"],
            }
        }
    }
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.60,  # Both at 50%, under threshold
        supplier_share_halt_threshold=0.80,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    assert events == []


def test_all_triggers_empty_feasible_set_only():
    """Test only empty feasible set event when concentration is fine"""
    supplier_registry = {
        "suppliers": {
            "s1": {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
            "s2": {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},
            "s3": {"supplier_id": "s3", "total_value_awarded": Decimal("100000")},
        }
    }
    tender_registry = {
        "tenders": {
            "t1": {
                "tender_id": "t1",
                "law_id": "law-123",
                "status": TenderStatus.EVALUATING,
                "feasible_suppliers": [],  # Empty!
                "requirements": [],
            }
        }
    }
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.50,  # Each has 33%, won't trigger
        supplier_share_halt_threshold=0.80,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    assert events[0].event_type == "EmptyFeasibleSetDetected"


def test_all_triggers_concentration_warning_only():
    """Test only concentration warning when feasible sets are fine"""
    supplier_registry = {
        "suppliers": {
            "s1": {"supplier_id": "s1", "total_value_awarded": Decimal("300000")},
            "s2": {"supplier_id": "s2", "total_value_awarded": Decimal("700000")},
        }
    }
    tender_registry = {
        "tenders": {
            "t1": {
                "tender_id": "t1",
                "status": TenderStatus.EVALUATING,
                "feasible_suppliers": ["s1", "s2"],
            }
        }
    }
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,  # s2 at 70% exceeds
        supplier_share_halt_threshold=0.80,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 1
    assert events[0].event_type == "SupplierConcentrationWarning"


def test_all_triggers_both_issues():
    """Test both empty feasible set and concentration events emitted"""
    supplier_registry = {
        "suppliers": {
            "s1": {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
            "s2": {"supplier_id": "s2", "total_value_awarded": Decimal("900000")},
        }
    }
    tender_registry = {
        "tenders": {
            "t1": {
                "tender_id": "t1",
                "law_id": "law-123",
                "status": TenderStatus.EVALUATING,
                "feasible_suppliers": [],  # Empty!
                "requirements": [],
            }
        }
    }
    policy = SafetyPolicy(
        supplier_share_warn_threshold=0.20,
        supplier_share_halt_threshold=0.35,
    )
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    assert len(events) == 2
    event_types = {e.event_type for e in events}
    assert event_types == {"EmptyFeasibleSetDetected", "SupplierConcentrationHalt"}


def test_all_triggers_filters_only_evaluating_tenders():
    """Test only EVALUATING tenders are checked for empty feasible sets"""
    supplier_registry = {"suppliers": {}}
    tender_registry = {
        "tenders": {
            "t1": {
                "tender_id": "t1",
                "status": TenderStatus.DRAFT,
                "feasible_suppliers": [],  # Empty but DRAFT
            },
            "t2": {
                "tender_id": "t2",
                "status": TenderStatus.OPEN,
                "feasible_suppliers": [],  # Empty but OPEN
            },
            "t3": {
                "tender_id": "t3",
                "law_id": "law-123",
                "status": TenderStatus.EVALUATING,
                "feasible_suppliers": [],  # Empty and EVALUATING
                "requirements": [],
            },
        }
    }
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    # Only t3 (EVALUATING) should trigger
    assert len(events) == 1
    assert events[0].payload["tender_id"] == "t3"


def test_all_triggers_empty_tender_registry():
    """Test no events when tender registry is empty"""
    supplier_registry = {"suppliers": {}}
    tender_registry = {}  # Missing 'tenders' key
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    events = evaluate_all_procurement_triggers(
        supplier_registry, tender_registry, policy, now
    )

    assert events == []
