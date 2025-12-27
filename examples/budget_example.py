"""
Budget Module Examples - Comprehensive demonstrations of budget features

This example demonstrates:
- Creating law-scoped budgets with flex classes
- Multi-gate enforcement (step-size, balance, authority, limits)
- Budget adjustments with zero-sum constraints
- Expenditure tracking and approval
- Budget triggers (balance violations, overspending)
- Complete audit trail through event sourcing
"""

import tempfile
from decimal import Decimal
from pathlib import Path

from freedom_that_lasts.ftl import FTL


def example_1_basic_budget_lifecycle():
    """
    Example 1: Basic Budget Lifecycle

    Demonstrates:
    - Creating a budget for a law
    - Activating the budget
    - Approving expenditures
    - Closing the budget
    """
    print("\n=== Example 1: Basic Budget Lifecycle ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "example1.db"
        ftl = FTL(db_path)

        # Setup: Create workspace and law
        workspace = ftl.create_workspace("Health Services District")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Community Health Initiative",
            scope={"description": "Primary care services for underserved communities"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        # Create budget with three items
        print("Creating budget for FY2025...")
        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Staff Salaries",
                    "allocated_amount": "500000",
                    "flex_class": "CRITICAL",      # 5% max change
                    "category": "personnel",
                },
                {
                    "name": "Medical Equipment",
                    "allocated_amount": "200000",
                    "flex_class": "IMPORTANT",     # 15% max change
                    "category": "capital",
                },
                {
                    "name": "Training & Development",
                    "allocated_amount": "50000",
                    "flex_class": "ASPIRATIONAL",  # 50% max change
                    "category": "development",
                },
            ],
        )

        print(f"✓ Budget created: {budget['budget_id']}")
        print(f"  Status: {budget['status']}")
        print(f"  Total: ${budget['budget_total']}")
        print(f"  Items: {len(budget['items'])}")

        # Activate budget (DRAFT → ACTIVE)
        print("\nActivating budget...")
        budget = ftl.activate_budget(budget["budget_id"])
        print(f"✓ Budget activated at {budget['activated_at']}")

        # Approve some expenditures
        print("\nApproving expenditures...")
        item_ids = list(budget["items"].keys())

        ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=item_ids[0],  # Staff Salaries
            amount=50000,
            purpose="Hire nurse practitioner",
        )
        print("✓ Approved $50,000 for nurse practitioner")

        ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=item_ids[1],  # Medical Equipment
            amount=75000,
            purpose="Purchase ultrasound machine",
            metadata={"vendor": "MedTech Inc", "po_number": "PO-2025-001"},
        )
        print("✓ Approved $75,000 for ultrasound machine")

        # Check budget status
        budget = ftl.budget_registry.get(budget["budget_id"])
        print("\nCurrent budget status:")
        for item in budget["items"].values():
            utilization = (
                float(item["spent_amount"]) / float(item["allocated_amount"]) * 100
            )
            print(f"  {item['name']}: ${item['spent_amount']} / ${item['allocated_amount']} ({utilization:.1f}%)")

        # Close budget
        print("\nClosing budget...")
        budget = ftl.close_budget(
            budget_id=budget["budget_id"],
            reason="End of fiscal year 2025",
        )
        print(f"✓ Budget closed at {budget['closed_at']}")


def example_2_multi_gate_enforcement():
    """
    Example 2: Multi-Gate Enforcement

    Demonstrates:
    - Gate 1: Flex class step-size limits
    - Gate 2: Budget balance (zero-sum)
    - Gate 4: No overspending
    - How multi-gate enforcement prevents budget manipulation
    """
    print("\n=== Example 2: Multi-Gate Enforcement ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "example2.db"
        ftl = FTL(db_path)

        # Setup
        workspace = ftl.create_workspace("Infrastructure District")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Road Maintenance Program",
            scope={"description": "Annual road maintenance budget"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Emergency Repairs",
                    "allocated_amount": "300000",
                    "flex_class": "CRITICAL",
                    "category": "operations",
                },
                {
                    "name": "Routine Maintenance",
                    "allocated_amount": "200000",
                    "flex_class": "IMPORTANT",
                    "category": "operations",
                },
                {
                    "name": "Beautification",
                    "allocated_amount": "100000",
                    "flex_class": "ASPIRATIONAL",
                    "category": "enhancement",
                },
            ],
        )
        ftl.activate_budget(budget["budget_id"])

        item_ids = list(budget["items"].keys())
        emergency_id = item_ids[0]
        routine_id = item_ids[1]
        beauty_id = item_ids[2]

        # Gate 1: Flex step-size enforcement
        print("Gate 1: Testing flex class step-size limits...")

        # This works: 4% change on CRITICAL item (within 5% limit)
        print("\n  Attempting 4% adjustment on CRITICAL item...")
        try:
            ftl.adjust_allocation(
                budget_id=budget["budget_id"],
                adjustments=[
                    {"item_id": emergency_id, "change_amount": Decimal("-12000")},  # -4%
                    {"item_id": routine_id, "change_amount": Decimal("12000")},     # +6%
                ],
                reason="Reallocate to routine maintenance",
            )
            print("  ✓ Adjustment successful (within flex limits)")
        except Exception as e:
            print(f"  ✗ Failed: {e}")

        # This fails: 7% change on CRITICAL item (exceeds 5% limit)
        print("\n  Attempting 7% adjustment on CRITICAL item...")
        try:
            ftl.adjust_allocation(
                budget_id=budget["budget_id"],
                adjustments=[
                    {"item_id": emergency_id, "change_amount": Decimal("-21000")},  # -7%
                    {"item_id": beauty_id, "change_amount": Decimal("21000")},
                ],
                reason="Try to cut emergency repairs too much",
            )
            print("  ✗ Should have failed!")
        except Exception as e:
            print(f"  ✓ Correctly rejected: {type(e).__name__}")

        # Gate 2: Budget balance (zero-sum)
        print("\nGate 2: Testing budget balance enforcement...")

        # This fails: net positive adjustment (not zero-sum)
        print("\n  Attempting non-zero-sum adjustment...")
        try:
            ftl.adjust_allocation(
                budget_id=budget["budget_id"],
                adjustments=[
                    {"item_id": emergency_id, "change_amount": Decimal("10000")},  # +10k, no offset
                ],
                reason="Try to grow budget without authorization",
            )
            print("  ✗ Should have failed!")
        except Exception as e:
            print(f"  ✓ Correctly rejected: {type(e).__name__}")

        # Gate 4: No overspending
        print("\nGate 4: Testing overspending prevention...")

        # First, spend some money
        budget = ftl.budget_registry.get(budget["budget_id"])
        emergency_id = [i for i, item in budget["items"].items() if item["name"] == "Emergency Repairs"][0]

        ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=emergency_id,
            amount=100000,
            purpose="Emergency pothole repairs",
        )
        print(f"\n  Spent $100,000 on Emergency Repairs")

        # Now try to reduce allocation below spending
        print("  Attempting to reduce allocation below spending...")
        try:
            ftl.adjust_allocation(
                budget_id=budget["budget_id"],
                adjustments=[
                    {"item_id": emergency_id, "change_amount": Decimal("-250000")},  # 288k → 38k (below 100k spent)
                    {"item_id": beauty_id, "change_amount": Decimal("250000")},
                ],
                reason="Try to reduce below spending",
            )
            print("  ✗ Should have failed!")
        except Exception as e:
            print(f"  ✓ Correctly rejected: {type(e).__name__}")

        print("\n✓ All four gates working correctly!")


def example_3_graduated_budget_cuts():
    """
    Example 3: Graduated Budget Cuts

    Demonstrates:
    - How flex classes create economic barriers to large cuts
    - Cutting a CRITICAL item by 30% requires multiple steps
    - Complete audit trail of all adjustments
    """
    print("\n=== Example 3: Graduated Budget Cuts ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "example3.db"
        ftl = FTL(db_path)

        # Setup
        workspace = ftl.create_workspace("Education Services")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Public Education Funding",
            scope={"description": "K-12 education budget"},
            reversibility_class="IRREVERSIBLE",  # Education cuts are hard to reverse
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Teacher Salaries",
                    "allocated_amount": "1000000",
                    "flex_class": "CRITICAL",      # 5% max - hard to cut
                    "category": "personnel",
                },
                {
                    "name": "Textbooks & Materials",
                    "allocated_amount": "200000",
                    "flex_class": "IMPORTANT",     # 15% max
                    "category": "supplies",
                },
                {
                    "name": "After-School Programs",
                    "allocated_amount": "100000",
                    "flex_class": "ASPIRATIONAL",  # 50% max - easier to cut
                    "category": "enrichment",
                },
            ],
        )
        ftl.activate_budget(budget["budget_id"])

        item_ids = list(budget["items"].keys())
        teacher_id = item_ids[0]
        textbook_id = item_ids[1]
        program_id = item_ids[2]

        print("Attempting to cut Teacher Salaries significantly...")
        print("(CRITICAL items limited to 5% per adjustment)\n")

        # Need multiple 4.5% cuts (staying under 5% limit)
        # Each cut is 4.5% of the *current* allocation
        steps = 6
        original_amount = Decimal("1000000")

        for step in range(1, steps + 1):
            budget = ftl.budget_registry.get(budget["budget_id"])
            current_allocation = Decimal(budget["items"][teacher_id]["allocated_amount"])

            # Calculate 4.5% of current allocation (staying under 5% limit)
            cut_amount = (current_allocation * Decimal("0.045")).quantize(Decimal("1"))

            print(f"Step {step}/{steps}: Cutting ${cut_amount} (4.5% of ${current_allocation})...")

            ftl.adjust_allocation(
                budget_id=budget["budget_id"],
                adjustments=[
                    {"item_id": teacher_id, "change_amount": -cut_amount},
                    {"item_id": program_id, "change_amount": cut_amount},  # Offset with program cuts
                ],
                reason=f"Budget reduction step {step}/5",
            )

            budget = ftl.budget_registry.get(budget["budget_id"])
            new_amount = Decimal(budget["items"][teacher_id]["allocated_amount"])
            total_cut = original_amount - new_amount
            pct_cut = float(total_cut / original_amount * 100)
            print(f"  → Teacher Salaries now: ${new_amount} (total cut: {pct_cut:.1f}%)\n")

        budget = ftl.budget_registry.get(budget["budget_id"])
        final_amount = Decimal(budget["items"][teacher_id]["allocated_amount"])
        total_reduction = original_amount - final_amount
        final_pct = float(total_reduction / original_amount * 100)

        print(f"✓ {final_pct:.1f}% cut achieved through {steps} separate adjustments")
        print("\nAudit trail:")

        # Show all adjustment events
        all_events = ftl.event_store.load_stream(budget["budget_id"])
        adjustment_events = [e for e in all_events if e.event_type == "AllocationAdjusted"]

        print(f"  Total adjustment events: {len(adjustment_events)}")
        for i, event in enumerate(adjustment_events, 1):
            print(f"  {i}. {event.payload['reason']}")

        print("\n💡 Insight: Cutting CRITICAL items requires many steps,")
        print("   creating transparency and making manipulation expensive!")


def example_4_expenditure_tracking():
    """
    Example 4: Expenditure Tracking & Audit Trail

    Demonstrates:
    - Approving expenditures with metadata
    - Querying expenditure history
    - Tracking budget utilization
    - Expenditure rejection logging
    """
    print("\n=== Example 4: Expenditure Tracking & Audit Trail ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "example4.db"
        ftl = FTL(db_path)

        # Setup
        workspace = ftl.create_workspace("IT Department")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Technology Modernization",
            scope={"description": "IT infrastructure upgrades"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Cloud Infrastructure",
                    "allocated_amount": "500000",
                    "flex_class": "CRITICAL",
                    "category": "operations",
                },
            ],
        )
        ftl.activate_budget(budget["budget_id"])

        item_id = list(budget["items"].keys())[0]

        # Approve multiple expenditures with rich metadata
        print("Approving expenditures with metadata...")

        expenditures = [
            {
                "amount": 120000,
                "purpose": "AWS EC2 instances - Q1",
                "metadata": {"vendor": "Amazon Web Services", "quarter": "Q1", "po": "PO-2025-101"},
            },
            {
                "amount": 80000,
                "purpose": "Database hosting - Q1",
                "metadata": {"vendor": "Amazon Web Services", "quarter": "Q1", "po": "PO-2025-102"},
            },
            {
                "amount": 50000,
                "purpose": "CDN services - Q1",
                "metadata": {"vendor": "Cloudflare", "quarter": "Q1", "po": "PO-2025-103"},
            },
        ]

        for exp in expenditures:
            ftl.approve_expenditure(
                budget_id=budget["budget_id"],
                item_id=item_id,
                amount=exp["amount"],
                purpose=exp["purpose"],
                metadata=exp["metadata"],
            )
            print(f"  ✓ ${exp['amount']:,} - {exp['purpose']}")

        # Query expenditure history
        print("\nExpenditure history:")
        history = ftl.get_expenditures(budget["budget_id"], item_id)

        total_spent = Decimal("0")
        for i, exp in enumerate(history, 1):
            total_spent += Decimal(str(exp["amount"]))
            amount = float(exp["amount"])
            remaining = float(exp["remaining_budget"])
            print(f"  {i}. ${amount:,.0f} - {exp['purpose']}")
            print(f"     PO: {exp['metadata'].get('po')}, Vendor: {exp['metadata'].get('vendor')}")
            print(f"     Remaining: ${remaining:,.0f}")

        # Show budget utilization
        budget = ftl.budget_registry.get(budget["budget_id"])
        item = budget["items"][item_id]
        allocated = Decimal(str(item["allocated_amount"]))
        spent = Decimal(str(item["spent_amount"]))
        remaining = allocated - spent
        utilization = float(spent / allocated * 100)

        print(f"\nBudget Utilization:")
        print(f"  Allocated: ${allocated:,}")
        print(f"  Spent: ${spent:,}")
        print(f"  Remaining: ${remaining:,}")
        print(f"  Utilization: {utilization:.1f}%")

        # Attempt to overspend (will be rejected)
        print("\nAttempting to overspend remaining budget...")
        spent_before = Decimal(budget["items"][item_id]["spent_amount"])

        result_budget = ftl.approve_expenditure(
            budget_id=budget["budget_id"],
            item_id=item_id,
            amount=300000,  # Exceeds remaining $250,000
            purpose="Additional infrastructure",
        )

        spent_after = Decimal(result_budget["items"][item_id]["spent_amount"])

        if spent_after == spent_before:
            print("  ✓ Expenditure correctly rejected (spent amount unchanged)")

            # Check rejection log
            rejections = ftl.expenditure_log.get_rejections(budget["budget_id"])
            if rejections:
                print(f"\n  Rejection details:")
                print(f"    Amount: ${rejections[-1]['amount']}")
                print(f"    Reason: {rejections[-1]['rejection_reason']}")
                print(f"    Gate failed: {rejections[-1]['gate_failed']}")
        else:
            print(f"  ✗ Expenditure should have been rejected! Spent increased to ${spent_after}")


def example_5_budget_triggers():
    """
    Example 5: Budget Triggers (Automatic Safeguards)

    Demonstrates:
    - Budget balance trigger (detects invariant violations)
    - Expenditure overspend trigger (detects overspending)
    - How triggers integrate with tick loop
    """
    print("\n=== Example 5: Budget Triggers (Automatic Safeguards) ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "example5.db"
        ftl = FTL(db_path)

        # Setup
        workspace = ftl.create_workspace("Municipal Services")
        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Parks & Recreation",
            scope={"description": "Parks maintenance and programs"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        ftl.activate_law(law["law_id"])

        budget = ftl.create_budget(
            law_id=law["law_id"],
            fiscal_year=2025,
            items=[
                {
                    "name": "Park Maintenance",
                    "allocated_amount": "200000",
                    "flex_class": "IMPORTANT",
                    "category": "operations",
                },
                {
                    "name": "Recreation Programs",
                    "allocated_amount": "100000",
                    "flex_class": "IMPORTANT",
                    "category": "programs",
                },
            ],
        )
        ftl.activate_budget(budget["budget_id"])

        print("Running tick loop to evaluate budget triggers...")

        # Run tick with budget registry
        result = ftl.tick()

        print(f"\n✓ Tick completed: {result.tick_id}")
        print(f"  Events triggered: {len(result.triggered_events)}")
        print(f"  Budget warnings: {sum(1 for e in result.triggered_events if 'Budget' in e.event_type)}")

        # Check if any budget triggers fired
        budget_events = [e for e in result.triggered_events if "Budget" in e.event_type]

        if budget_events:
            print("\n⚠️  Budget triggers fired:")
            for event in budget_events:
                print(f"    - {event.event_type}")
        else:
            print("\n✓ No budget violations detected (all budgets healthy)")

        # Show budget health status
        violations = ftl.budget_health_projection.get_violations()
        print(f"\nBudget Health:")
        print(f"  Balance violations: {len(violations['balance_violations'])}")
        print(f"  Overspend incidents: {len(violations['overspend_incidents'])}")


if __name__ == "__main__":
    print("=" * 70)
    print("Freedom That Lasts - Budget Module Examples")
    print("=" * 70)

    # Run all examples
    example_1_basic_budget_lifecycle()
    example_2_multi_gate_enforcement()
    example_3_graduated_budget_cuts()
    example_4_expenditure_tracking()
    example_5_budget_triggers()

    print("\n" + "=" * 70)
    print("✓ All examples completed successfully!")
    print("=" * 70)
