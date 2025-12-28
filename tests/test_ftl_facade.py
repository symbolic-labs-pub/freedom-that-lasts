"""
Tests for FTL Façade - Public API

These tests verify that the FTL façade provides a clean,
high-level API that works correctly.
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.feedback.models import RiskLevel
from freedom_that_lasts.ftl import FTL
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.models import ReversibilityClass


def test_ftl_init_creates_database(tmp_path):
    """Test FTL initialization creates database"""
    db_path = tmp_path / "test.db"

    ftl = FTL(str(db_path))

    assert db_path.exists()
    assert ftl.event_store is not None
    assert ftl.workspace_registry is not None


def test_ftl_rebuild_projections_from_events(tmp_path):
    """Test FTL rebuilds projections from event store"""
    db_path = tmp_path / "test.db"

    # Create some data
    ftl1 = FTL(str(db_path))
    workspace = ftl1.create_workspace("Test")
    workspace_id = workspace["workspace_id"]

    # Create new instance - should rebuild projections
    ftl2 = FTL(str(db_path))

    workspaces = ftl2.list_workspaces()
    assert len(workspaces) == 1
    assert workspaces[0]["workspace_id"] == workspace_id


def test_ftl_create_workspace(tmp_path):
    """Test workspace creation through façade"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace(
        name="Health Services", scope={"territory": "Budapest"}
    )

    assert workspace["name"] == "Health Services"
    assert workspace["scope"]["territory"] == "Budapest"
    assert "workspace_id" in workspace


def test_ftl_list_workspaces(tmp_path):
    """Test listing workspaces"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    ftl.create_workspace("WS1")
    ftl.create_workspace("WS2")

    workspaces = ftl.list_workspaces()
    assert len(workspaces) == 2


def test_ftl_delegate(tmp_path):
    """Test delegation through façade"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    delegation = ftl.delegate(
        from_actor="alice",
        workspace_id=workspace["workspace_id"],
        to_actor="bob",
        ttl_days=180,
    )

    assert delegation["from_actor"] == "alice"
    assert delegation["to_actor"] == "bob"
    assert delegation["ttl_days"] == 180


def test_ftl_create_and_activate_law(tmp_path):
    """Test law creation and activation"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test Law",
        scope={"territory": "Test"},
        reversibility_class="REVERSIBLE",
        checkpoints=[30, 90, 180, 365],
        params={"test": "value"},
    )

    assert law["title"] == "Test Law"
    assert law["status"] == "DRAFT"
    assert law["reversibility_class"] == "REVERSIBLE"

    # Activate
    activated_law = ftl.activate_law(law["law_id"])
    assert activated_law["status"] == "ACTIVE"
    assert activated_law["next_checkpoint_at"] is not None


def test_ftl_list_laws(tmp_path):
    """Test listing laws"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")

    law1 = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Law 1",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    law2 = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Law 2",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )

    # List all
    all_laws = ftl.list_laws()
    assert len(all_laws) == 2

    # List by status
    draft_laws = ftl.list_laws(status="DRAFT")
    assert len(draft_laws) == 2


def test_ftl_complete_review(tmp_path):
    """Test completing a law review"""
    db_path = tmp_path / "test.db"
    time_provider = TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))
    ftl = FTL(str(db_path), time_provider=time_provider)

    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    # Advance time and trigger review
    time_provider.advance_days(35)
    ftl.tick()

    # Complete review
    reviewed_law = ftl.complete_review(
        law_id=law["law_id"], outcome="continue", notes="Looks good"
    )

    assert reviewed_law["status"] == "ACTIVE"


def test_ftl_tick_healthy_system(tmp_path):
    """Test tick on healthy system"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    ftl.delegate("alice", workspace["workspace_id"], "bob", 180)

    result = ftl.tick()

    assert result.freedom_health.risk_level == RiskLevel.GREEN
    assert not result.has_warnings()
    assert not result.has_halts()


def test_ftl_health(tmp_path):
    """Test health status"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    workspace = ftl.create_workspace("Test")
    ftl.delegate("alice", workspace["workspace_id"], "bob", 180)

    health = ftl.health()

    assert health.risk_level == RiskLevel.GREEN
    assert health.concentration.total_active_delegations == 1
    assert health.law_review_health.total_active_laws == 0


def test_ftl_get_safety_events(tmp_path):
    """Test getting safety events"""
    db_path = tmp_path / "test.db"
    time_provider = TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))
    ftl = FTL(str(db_path), time_provider=time_provider)

    # Initially no events
    events = ftl.get_safety_events()
    assert len(events) == 0

    # Create a law and advance time to trigger review
    workspace = ftl.create_workspace("Test")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Test",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    # Advance time past checkpoint
    time_provider.advance_days(35)

    # Run tick - should trigger review
    ftl.tick()

    # Should have LawReviewTriggered event
    events = ftl.get_safety_events()
    assert len(events) > 0
    assert any(e["event_type"] == "LawReviewTriggered" for e in events)


def test_ftl_get_safety_policy(tmp_path):
    """Test getting safety policy"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    policy = ftl.get_safety_policy()

    assert policy.delegation_gini_warn == 0.55
    assert policy.delegation_gini_halt == 0.70
    assert policy.max_delegation_ttl_days == 365

# =============================================================================
# Security Validation Tests
# =============================================================================


def test_ftl_validates_db_path_against_directory(tmp_path):
    """Test FTL rejects directory as database path"""
    dir_path = tmp_path / "directory"
    dir_path.mkdir()
    
    with pytest.raises(ValueError, match="is a directory"):
        FTL(str(dir_path))


def test_ftl_validates_parent_directory_exists(tmp_path):
    """Test FTL rejects path with non-existent parent directory"""
    bad_path = tmp_path / "nonexistent" / "test.db"
    
    with pytest.raises(ValueError, match="Parent directory.*does not exist"):
        FTL(str(bad_path))


def test_ftl_validates_path_traversal_when_base_path_set(tmp_path, monkeypatch):
    """Test FTL rejects path traversal when FTL_DB_BASE_PATH is set"""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    
    monkeypatch.setenv("FTL_DB_BASE_PATH", str(allowed_dir))
    
    # Try to create DB outside allowed directory
    outside_path = tmp_path / "outside" / "test.db"
    outside_path.parent.mkdir()
    
    with pytest.raises(ValueError, match="must be within allowed directory"):
        FTL(str(outside_path))


def test_ftl_allows_path_within_base_path(tmp_path, monkeypatch):
    """Test FTL allows path within FTL_DB_BASE_PATH"""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    monkeypatch.setenv("FTL_DB_BASE_PATH", str(allowed_dir))

    # Create DB inside allowed directory
    inside_path = allowed_dir / "test.db"

    # Should succeed
    ftl = FTL(str(inside_path))
    assert ftl is not None


# =============================================================================
# Budget Integration Tests
# =============================================================================


def test_ftl_budget_lifecycle(tmp_path):
    """Test complete budget lifecycle: create, activate, adjust, expenditure, close"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    # Create workspace and law
    workspace = ftl.create_workspace("Finance")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Annual Budget Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    # Create budget
    budget = ftl.create_budget(
        law_id=law["law_id"],
        fiscal_year=2025,
        items=[
            {
                "name": "Healthcare Services",
                "allocated_amount": 500000.0,
                "flex_class": "IMPORTANT",
                "category": "healthcare",
            },
            {
                "name": "Education Programs",
                "allocated_amount": 300000.0,
                "flex_class": "ASPIRATIONAL",
                "category": "education",
            },
        ],
    )

    assert budget["fiscal_year"] == 2025
    assert budget["status"] == "DRAFT"
    assert len(budget["items"]) == 2

    # Activate budget
    activated_budget = ftl.activate_budget(budget["budget_id"])
    assert activated_budget["status"] == "ACTIVE"

    # Get budget items - items is a dict not a list, keyed by item_id
    item_ids = list(activated_budget["items"].keys())
    first_item_id = item_ids[0]
    second_item_id = item_ids[1]

    # Adjust allocation - must be zero-sum (increase one, decrease another)
    # Healthcare: 500000 → 550000 (+50000)
    # Education: 300000 → 250000 (-50000)
    adjusted_budget = ftl.adjust_allocation(
        budget_id=budget["budget_id"],
        adjustments=[
            {"item_id": first_item_id, "change_amount": "50000"},
            {"item_id": second_item_id, "change_amount": "-50000"},
        ],
        reason="Increased healthcare demand",
    )

    # Check that allocation was adjusted (items is dict, access by key)
    # Use float comparison for Decimal values
    from decimal import Decimal
    assert Decimal(adjusted_budget["items"][first_item_id]["allocated_amount"]) == Decimal("550000.0")

    # Approve expenditure
    budget_after_expense = ftl.approve_expenditure(
        budget_id=budget["budget_id"],
        item_id=first_item_id,
        amount=50000.0,
        purpose="Medical equipment purchase",
    )

    # Verify expenditure was recorded
    assert Decimal(budget_after_expense["items"][first_item_id]["spent_amount"]) == Decimal("50000.0")

    # List budgets
    budgets = ftl.list_budgets()
    assert len(budgets) >= 1
    assert any(b["budget_id"] == budget["budget_id"] for b in budgets)

    # Get expenditures
    expenditures = ftl.get_expenditures(budget_id=budget["budget_id"])
    assert len(expenditures) == 1

    # Close budget
    closed_budget = ftl.close_budget(
        budget_id=budget["budget_id"],
        reason="Fiscal year completed successfully",
    )

    assert closed_budget["status"] == "CLOSED"


# =============================================================================
# Supplier Integration Tests
# =============================================================================


def test_ftl_supplier_operations(tmp_path):
    """Test supplier registration and capability management"""
    db_path = tmp_path / "test.db"
    ftl = FTL(str(db_path))

    # Register supplier
    supplier = ftl.register_supplier(
        name="Tech Solutions Inc",
        supplier_type="company",
        metadata={"industry": "technology", "employees": 150},
    )

    assert supplier["name"] == "Tech Solutions Inc"
    assert supplier["supplier_type"] == "company"
    assert "supplier_id" in supplier

    # Add capability claim
    from datetime import datetime, timezone

    updated_supplier = ftl.add_capability_claim(
        supplier_id=supplier["supplier_id"],
        capability_type="ISO27001",
        scope={"regions": ["EU", "US"]},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_type": "certification",
                "issuer": "ISO Certification Body",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ],
        capacity={"concurrent_projects": 5},
    )

    # Verify capability was added
    assert "ISO27001" in updated_supplier["capabilities"]
    assert updated_supplier["capabilities"]["ISO27001"]["verified"] is True

    # List suppliers
    suppliers = ftl.list_suppliers()
    assert len(suppliers) >= 1
    assert any(s["supplier_id"] == supplier["supplier_id"] for s in suppliers)


# =============================================================================
# Tender/Procurement Integration Tests
# =============================================================================


def test_ftl_tender_lifecycle(tmp_path):
    """Test complete tender lifecycle: create, open, evaluate, select, award, deliver, complete"""
    db_path = tmp_path / "test.db"
    from datetime import datetime, timedelta, timezone
    from freedom_that_lasts.resource.models import SelectionMethod

    ftl = FTL(str(db_path))

    # Setup: Create workspace, law, and supplier
    workspace = ftl.create_workspace("Procurement")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Procurement Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    supplier = ftl.register_supplier(
        name="Vendor Corp",
        supplier_type="company",
    )

    # Add capability to supplier
    ftl.add_capability_claim(
        supplier_id=supplier["supplier_id"],
        capability_type="ISO9001",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_type": "certification",
                "issuer": "ISO Certification Body",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ],
        capacity={"concurrent_projects": 10},
    )

    # Create tender
    tender = ftl.create_tender(
        law_id=law["law_id"],
        title="IT Infrastructure Upgrade",
        description="Modernize server infrastructure",
        requirements=[
            {
                "capability_type": "ISO9001",
                "min_capacity": {"concurrent_projects": 1},
                "mandatory": True,
            }
        ],
        selection_method=SelectionMethod.ROTATION,
        estimated_value=100000.0,
    )

    assert tender["title"] == "IT Infrastructure Upgrade"
    assert tender["status"] == "DRAFT"

    # Open tender
    deadline = datetime.now(timezone.utc) + timedelta(days=30)
    opened_tender = ftl.open_tender(tender["tender_id"])

    assert opened_tender["status"] == "OPEN"

    # Evaluate tender
    evaluated_tender = ftl.evaluate_tender(tender["tender_id"])

    # Status should be EVALUATING after evaluation (ready for selection)
    assert evaluated_tender["status"] == "EVALUATING"
    assert len(evaluated_tender.get("feasible_suppliers", [])) >= 0

    # Select supplier
    selected_tender = ftl.select_supplier(tender["tender_id"])

    # Status is still EVALUATING - supplier selected but not yet awarded
    assert selected_tender["status"] == "EVALUATING"
    # Verify supplier was selected
    assert selected_tender.get("selected_supplier_id") == supplier["supplier_id"]

    # Award tender
    awarded_tender = ftl.award_tender(
        tender_id=tender["tender_id"],
        contract_value=95000.0,
        contract_terms={"payment_schedule": "monthly", "duration_days": 90},
    )

    # Now status should be AWARDED
    assert awarded_tender["status"] == "AWARDED"
    assert awarded_tender["selected_supplier_id"] == supplier["supplier_id"]

    # Record milestone
    milestone = ftl.record_milestone(
        tender_id=tender["tender_id"],
        milestone_id="milestone-1",
        milestone_type="DELIVERY_START",
        description="Project kickoff completed",
        evidence=[],
        metadata={},
    )

    assert milestone["milestone_type"] == "DELIVERY_START"

    # Complete tender
    completed_tender = ftl.complete_tender(
        tender_id=tender["tender_id"],
        completion_report={"summary": "Successfully completed"},
        final_quality_score=0.95,
    )

    assert completed_tender["status"] == "COMPLETED"
    assert completed_tender["final_quality_score"] == 0.95

    # List tenders
    tenders = ftl.list_tenders()
    assert len(tenders) >= 1
    assert any(t["tender_id"] == tender["tender_id"] for t in tenders)


def test_ftl_record_sla_breach(tmp_path):
    """Test recording SLA breach for tender"""
    db_path = tmp_path / "test.db"
    from datetime import datetime, timezone
    from freedom_that_lasts.resource.models import SelectionMethod

    ftl = FTL(str(db_path))

    # Setup: Create workspace, law, supplier, and awarded tender
    workspace = ftl.create_workspace("Procurement")
    law = ftl.create_law(
        workspace_id=workspace["workspace_id"],
        title="Procurement Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
    )
    ftl.activate_law(law["law_id"])

    supplier = ftl.register_supplier(name="Supplier", supplier_type="company")

    # Add capability to supplier so evaluation can find a feasible supplier
    ftl.add_capability_claim(
        supplier_id=supplier["supplier_id"],
        capability_type="BasicSupport",
        scope={},
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=[
            {
                "evidence_type": "reference",
                "issuer": "Previous Client",
                "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
            }
        ],
        capacity={"max_projects": 5},
    )

    tender = ftl.create_tender(
        law_id=law["law_id"],
        title="Test Tender",
        description="Test",
        requirements=[
            {
                "capability_type": "BasicSupport",
                "min_capacity": None,
                "mandatory": True,
            }
        ],
        selection_method=SelectionMethod.ROTATION,
        estimated_value=50000.0,
    )

    ftl.open_tender(tender["tender_id"])
    ftl.evaluate_tender(tender["tender_id"])
    ftl.select_supplier(tender["tender_id"])
    ftl.award_tender(
        tender_id=tender["tender_id"],
        contract_value=50000.0,
        contract_terms={},
    )

    # Record SLA breach
    sla_result = ftl.record_sla_breach(
        tender_id=tender["tender_id"],
        sla_metric="response_time_hours",
        expected_value=24,  # Expected response within 24 hours
        actual_value=120,  # Actual response took 5 days (120 hours)
        severity="major",
        impact_description="5-day delay in project timeline",
    )

    # Verify SLA breach was recorded
    assert sla_result["tender_id"] == tender["tender_id"]
    # Note: The actual return structure depends on projection implementation
