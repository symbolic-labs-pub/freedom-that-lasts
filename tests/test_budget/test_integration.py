"""
Integration tests for Budget Module through FTL Façade

These tests verify end-to-end budget workflows including:
- Law → Budget → Activate → Adjust → Expenditure → Close
- Multi-gate enforcement through the façade
- Projection rebuilding from event store
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from freedom_that_lasts.budget.models import BudgetStatus
from freedom_that_lasts.ftl import FTL
from freedom_that_lasts.kernel.errors import (
    AllocationBelowSpending,
    BudgetBalanceViolation,
    BudgetNotFound,
    FlexStepSizeViolation,
)


@pytest.fixture
def ftl_with_law():
    """Create FTL instance with a law for budget testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ftl = FTL(db_path)

        # Create workspace
        workspace = ftl.create_workspace("Test Workspace")

        # Create law
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Test Law",
            scope={"description": "Law for budget testing"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
            actor_id="alice",
        )

        ftl.activate_law(law["law_id"], actor_id="alice")

        yield ftl, law["law_id"]


def test_budget_full_lifecycle(ftl_with_law):
    """Test complete budget lifecycle: create → activate → adjust → expenditure → close"""
    ftl, law_id = ftl_with_law

    # Create budget
    budget = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Staff Salaries",
                "allocated_amount": "500000",
                "flex_class": "CRITICAL",
                "category": "personnel",
            },
            {
                "name": "Equipment",
                "allocated_amount": "200000",
                "flex_class": "IMPORTANT",
                "category": "capital",
            },
            {
                "name": "Training",
                "allocated_amount": "50000",
                "flex_class": "ASPIRATIONAL",
                "category": "development",
            },
        ],
        actor_id="alice",
    )

    assert budget["law_id"] == law_id
    assert budget["fiscal_year"] == 2025
    assert budget["status"] == BudgetStatus.DRAFT.value
    assert budget["budget_total"] == "750000"
    assert len(budget["items"]) == 3

    # Activate budget
    budget = ftl.activate_budget(budget["budget_id"], actor_id="alice")
    assert budget["status"] == BudgetStatus.ACTIVE.value
    assert budget["activated_at"] is not None

    # Adjust allocation (zero-sum: -25k from staff, +25k to equipment)
    staff_item_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Staff Salaries"
    ][0]
    equipment_item_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Equipment"
    ][0]

    budget = ftl.adjust_allocation(
        budget_id=budget["budget_id"],
        adjustments=[
            {"item_id": staff_item_id, "change_amount": Decimal("-25000")},  # -5%
            {"item_id": equipment_item_id, "change_amount": Decimal("25000")},  # +12.5%
        ],
        reason="Reallocate for new equipment",
        actor_id="alice",
    )

    assert budget["items"][staff_item_id]["allocated_amount"] == "475000"
    assert budget["items"][equipment_item_id]["allocated_amount"] == "225000"

    # Approve expenditure
    budget = ftl.approve_expenditure(
        budget_id=budget["budget_id"],
        item_id=staff_item_id,
        amount=50000,
        purpose="Hire data analyst",
        actor_id="alice",
    )

    assert budget["items"][staff_item_id]["spent_amount"] == "50000"

    # Check expenditure log
    expenditures = ftl.get_expenditures(budget["budget_id"], staff_item_id)
    assert len(expenditures) == 1
    assert expenditures[0]["amount"] == "50000"
    assert expenditures[0]["purpose"] == "Hire data analyst"

    # Close budget
    budget = ftl.close_budget(
        budget_id=budget["budget_id"],
        reason="End of fiscal year 2025",
        actor_id="alice",
    )

    assert budget["status"] == BudgetStatus.CLOSED.value
    assert budget["closed_at"] is not None


def test_budget_multi_gate_enforcement_step_size(ftl_with_law):
    """Test that Gate 1 (step-size limits) is enforced"""
    ftl, law_id = ftl_with_law

    budget = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Critical Item",
                "allocated_amount": "100000",
                "flex_class": "CRITICAL",  # 5% max
                "category": "test",
            },
            {
                "name": "Buffer",
                "allocated_amount": "50000",
                "flex_class": "IMPORTANT",
                "category": "test",
            },
        ],
    )

    ftl.activate_budget(budget["budget_id"])

    critical_item_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Critical Item"
    ][0]
    buffer_item_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Buffer"
    ][0]

    # Try to change critical item by 6% (exceeds 5% limit)
    with pytest.raises(FlexStepSizeViolation) as exc_info:
        ftl.adjust_allocation(
            budget_id=budget["budget_id"],
            adjustments=[
                {"item_id": critical_item_id, "change_amount": Decimal("-6000")},  # 6%
                {"item_id": buffer_item_id, "change_amount": Decimal("6000")},
            ],
            reason="Test",
        )

    assert exc_info.value.flex_class == "CRITICAL"
    assert exc_info.value.max_percent == 0.05


def test_budget_multi_gate_enforcement_balance(ftl_with_law):
    """Test that Gate 2 (budget balance) is enforced"""
    ftl, law_id = ftl_with_law

    budget = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Item 1",
                "allocated_amount": "100000",
                "flex_class": "IMPORTANT",
                "category": "test",
            },
        ],
    )

    ftl.activate_budget(budget["budget_id"])

    item_id = list(budget["items"].keys())[0]

    # Try to create net positive adjustment (breaks zero-sum)
    with pytest.raises(BudgetBalanceViolation) as exc_info:
        ftl.adjust_allocation(
            budget_id=budget["budget_id"],
            adjustments=[
                {"item_id": item_id, "change_amount": Decimal("10000")},  # +10k, no offset
            ],
            reason="Test",
        )

    assert exc_info.value.variance == "10000"


def test_budget_multi_gate_enforcement_overspending(ftl_with_law):
    """Test that Gate 4 (no overspending) is enforced"""
    ftl, law_id = ftl_with_law

    budget = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Item 1",
                "allocated_amount": "100000",
                "flex_class": "ASPIRATIONAL",  # 50% max
                "category": "test",
            },
            {
                "name": "Item 2",
                "allocated_amount": "100000",
                "flex_class": "ASPIRATIONAL",  # 50% max (allows large increase)
                "category": "test",
            },
        ],
    )

    ftl.activate_budget(budget["budget_id"])

    item1_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Item 1"
    ][0]
    item2_id = [
        i["item_id"] for i in budget["items"].values() if i["name"] == "Item 2"
    ][0]

    # Spend 60k on item 1
    ftl.approve_expenditure(
        budget_id=budget["budget_id"],
        item_id=item1_id,
        amount=60000,
        purpose="Test spending",
    )

    # Try to reduce item 1 allocation to 55k (below 60k spent)
    # This should pass Gate 1 (45% change within ASPIRATIONAL 50% limit)
    # and Gate 2 (zero-sum), but fail Gate 4 (allocation below spending)
    with pytest.raises(AllocationBelowSpending):
        ftl.adjust_allocation(
            budget_id=budget["budget_id"],
            adjustments=[
                {"item_id": item1_id, "change_amount": Decimal("-45000")},  # 100k → 55k (45% change, but below 60k spent)
                {"item_id": item2_id, "change_amount": Decimal("45000")},  # 100k → 145k (45% change)
            ],
            reason="Test",
        )


def test_budget_list_operations(ftl_with_law):
    """Test listing budgets by law and status"""
    ftl, law_id = ftl_with_law

    # Create multiple budgets
    budget1 = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Item 1",
                "allocated_amount": "100000",
                "flex_class": "IMPORTANT",
                "category": "test",
            }
        ],
    )

    budget2 = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2026,
        items=[
            {
                "name": "Item 2",
                "allocated_amount": "200000",
                "flex_class": "CRITICAL",
                "category": "test",
            }
        ],
    )

    # Activate one budget
    ftl.activate_budget(budget1["budget_id"])

    # List by law
    law_budgets = ftl.list_budgets(law_id=law_id)
    assert len(law_budgets) == 2
    assert all(b["law_id"] == law_id for b in law_budgets)

    # List by status
    draft_budgets = ftl.list_budgets(status="DRAFT")
    assert len(draft_budgets) == 1
    assert draft_budgets[0]["budget_id"] == budget2["budget_id"]

    active_budgets = ftl.list_budgets(status="ACTIVE")
    assert len(active_budgets) == 1
    assert active_budgets[0]["budget_id"] == budget1["budget_id"]


def test_budget_projection_rebuilding(ftl_with_law):
    """Test that projections rebuild correctly from event store"""
    ftl, law_id = ftl_with_law

    # Create and activate budget
    budget = ftl.create_budget(
        law_id=law_id,
        fiscal_year=2025,
        items=[
            {
                "name": "Test Item",
                "allocated_amount": "100000",
                "flex_class": "IMPORTANT",
                "category": "test",
            }
        ],
    )

    ftl.activate_budget(budget["budget_id"])

    item_id = list(budget["items"].keys())[0]

    # Approve expenditure
    ftl.approve_expenditure(
        budget_id=budget["budget_id"],
        item_id=item_id,
        amount=25000,
        purpose="Test",
    )

    # Create new FTL instance (rebuilds from event store)
    ftl2 = FTL(ftl.sqlite_path)

    # Verify budget state is correct
    rebuilt_budget = ftl2.budget_registry.get(budget["budget_id"])
    assert rebuilt_budget is not None
    assert rebuilt_budget["status"] == BudgetStatus.ACTIVE.value
    assert rebuilt_budget["items"][item_id]["spent_amount"] == "25000"

    # Verify expenditure log is correct
    expenditures = ftl2.get_expenditures(budget["budget_id"])
    assert len(expenditures) == 1
    assert expenditures[0]["amount"] == "25000"


def test_budget_expenditure_rejection():
    """Test that expenditure rejection is logged properly"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ftl = FTL(db_path)

        # Create workspace and law
        workspace = ftl.create_workspace("Test")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Test Law",
            scope={"description": "Test"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        # Create DRAFT budget (not activated)
        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Item",
                    "allocated_amount": "100000",
                    "flex_class": "IMPORTANT",
                    "category": "test",
                }
            ],
        )

        item_id = list(budget["items"].keys())[0]

        # Try to approve expenditure on DRAFT budget (should be rejected)
        budget_result = ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=item_id,
            amount=10000,
            purpose="Test",
        )

        # Budget state should not change (rejection doesn't modify budget)
        assert budget_result["items"][item_id]["spent_amount"] == "0"

        # Check rejection log
        rejections = ftl.expenditure_log.get_rejections(budget["budget_id"])
        assert len(rejections) == 1
        assert rejections[0]["gate_failed"] == "budget_status"
        assert "ACTIVE" in rejections[0]["rejection_reason"]


def test_budget_not_found():
    """Test that BudgetNotFound is raised for non-existent budget"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ftl = FTL(db_path)

        with pytest.raises(BudgetNotFound):
            ftl.activate_budget("nonexistent-budget-id")


def test_budget_metadata_preservation():
    """Test that metadata is preserved through budget operations"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ftl = FTL(db_path)

        workspace = ftl.create_workspace("Test")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Test Law",
            scope={"description": "Test"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        # Create budget with metadata
        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Item",
                    "allocated_amount": "100000",
                    "flex_class": "IMPORTANT",
                    "category": "infrastructure",
                }
            ],
        )

        ftl.activate_budget(budget["budget_id"])

        item_id = list(budget["items"].keys())[0]

        # Approve expenditure with metadata
        ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=item_id,
            amount=25000,
            purpose="Server upgrade",
            metadata={"department": "IT", "vendor": "TechCorp"},
        )

        # Check expenditure metadata
        expenditures = ftl.get_expenditures(budget["budget_id"])
        assert expenditures[0]["metadata"]["department"] == "IT"
        assert expenditures[0]["metadata"]["vendor"] == "TechCorp"
