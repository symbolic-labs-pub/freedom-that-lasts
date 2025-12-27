"""
Quick Integration Test for v0.3 Procurement Module

Tests the full procurement workflow end-to-end:
1. Create law (prerequisite)
2. Register suppliers with capabilities
3. Create tender with requirements
4. Open tender
5. Evaluate tender (binary matching)
6. Select supplier (constitutional selection)
7. Award tender
8. Complete tender (reputation update)
9. Run tick (triggers)
"""

import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from freedom_that_lasts import FTL
from freedom_that_lasts.resource.models import SelectionMethod


def test_full_procurement_workflow():
    """Test complete procurement workflow"""
    print("\n" + "=" * 70)
    print("🧪 v0.3 Procurement Integration Test")
    print("=" * 70)

    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ftl = FTL(str(db_path))

        # Step 1: Create workspace and law (prerequisite for tender)
        print("\n📋 Step 1: Create workspace and law...")
        workspace = ftl.create_workspace(
            name="Infrastructure",
            scope={"territory": "Budapest"},
        )
        print(f"  ✓ Created workspace: {workspace['workspace_id']}")

        law = ftl.create_law(
            workspace_id=workspace["workspace_id"],
            title="Data Center Infrastructure Law",
            scope={"description": "Public cloud infrastructure"},
            reversibility_class="SEMI_REVERSIBLE",
            checkpoints=[30, 90, 180, 365],
        )
        print(f"  ✓ Created law: {law['law_id']}")

        # Activate law (required for tender)
        ftl.activate_law(law["law_id"])
        print(f"  ✓ Activated law")

        # Step 2: Register suppliers with capabilities
        print("\n🏢 Step 2: Register suppliers with evidence-based capabilities...")

        # Supplier 1: Has ISO27001
        supplier1 = ftl.register_supplier(
            name="SecureInfraCo",
            supplier_type="company",
            metadata={"contact": "ops@secureinfra.com"},
        )
        print(f"  ✓ Registered supplier 1: {supplier1['supplier_id']}")

        ftl.add_capability_claim(
            supplier_id=supplier1["supplier_id"],
            capability_type="ISO27001",
            scope={"territories": ["EU"], "max_concurrent": 5},
            valid_from=datetime(2024, 1, 1),
            valid_until=datetime(2027, 1, 1),
            evidence=[
                {
                    "evidence_type": "certification",
                    "issuer": "ISO Certification Body",
                    "issued_at": "2024-01-01T00:00:00Z",
                    "valid_until": "2027-01-01T00:00:00Z",
                    "document_uri": "https://cert.example.com/ISO27001/1234",
                }
            ],
            capacity={"throughput": "20 servers/month", "ramp_up_days": 14},
        )
        print(f"  ✓ Added ISO27001 capability to supplier 1")

        # Supplier 2: Has ISO27001 AND 24/7 support
        supplier2 = ftl.register_supplier(
            name="CloudProSystems",
            supplier_type="company",
            metadata={"contact": "sales@cloudpro.com"},
        )
        print(f"  ✓ Registered supplier 2: {supplier2['supplier_id']}")

        ftl.add_capability_claim(
            supplier_id=supplier2["supplier_id"],
            capability_type="ISO27001",
            scope={"territories": ["EU", "US"], "max_concurrent": 10},
            valid_from=datetime(2024, 1, 1),
            valid_until=datetime(2027, 1, 1),
            evidence=[
                {
                    "evidence_type": "certification",
                    "issuer": "ISO Certification Body",
                    "issued_at": "2024-01-01T00:00:00Z",
                    "valid_until": "2027-01-01T00:00:00Z",
                    "document_uri": "https://cert.example.com/ISO27001/5678",
                }
            ],
            capacity={"throughput": "50 servers/month", "ramp_up_days": 7},
        )

        ftl.add_capability_claim(
            supplier_id=supplier2["supplier_id"],
            capability_type="24_7_support",
            scope={"response_time_minutes": 30},
            valid_from=datetime(2024, 1, 1),
            valid_until=None,  # No expiry
            evidence=[
                {
                    "evidence_type": "reference",
                    "issuer": "PreviousClient",
                    "issued_at": "2024-06-01T00:00:00Z",
                    "document_uri": "https://reference.example.com/support-sla",
                }
            ],
        )
        print(f"  ✓ Added ISO27001 + 24/7 support to supplier 2")

        # Supplier 3: Only has 24/7 support (will be excluded)
        supplier3 = ftl.register_supplier(
            name="SupportOnlyCo",
            supplier_type="company",
        )
        print(f"  ✓ Registered supplier 3: {supplier3['supplier_id']}")

        ftl.add_capability_claim(
            supplier_id=supplier3["supplier_id"],
            capability_type="24_7_support",
            scope={"response_time_minutes": 15},
            valid_from=datetime(2024, 1, 1),
            valid_until=None,
            evidence=[
                {
                    "evidence_type": "reference",
                    "issuer": "Client",
                    "issued_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        print(f"  ✓ Added 24/7 support to supplier 3 (no ISO27001)")

        # Step 3: Create tender with requirements
        print("\n📝 Step 3: Create tender with binary requirements...")
        tender = ftl.create_tender(
            law_id=law["law_id"],
            title="Data Center Server Procurement",
            description="50 servers for public health data platform",
            requirements=[
                {"capability_type": "ISO27001", "mandatory": True},
                # Note: NOT requiring 24/7 support, so supplier1 and supplier2 should be feasible
            ],
            required_capacity=None,  # Not checking capacity for this test (focus on capability matching)
            sla_requirements={"uptime": 0.999, "response_time_hours": 4},
            evidence_required=["certification"],
            estimated_value=Decimal("500000"),
            selection_method=SelectionMethod.ROTATION_WITH_RANDOM,
        )
        print(f"  ✓ Created tender: {tender['tender_id']}")
        print(f"    - Status: {tender['status']}")
        print(f"    - Requirements: ISO27001 (mandatory)")

        # Step 4: Open tender
        print("\n🚪 Step 4: Open tender for submissions...")
        tender = ftl.open_tender(tender["tender_id"])
        print(f"  ✓ Opened tender")
        print(f"    - Status: {tender['status']}")

        # Step 5: Evaluate tender (binary matching)
        print("\n🔍 Step 5: Evaluate tender (binary requirement matching)...")
        tender = ftl.evaluate_tender(tender["tender_id"])
        print(f"  ✓ Evaluated tender")
        print(f"    - Status: {tender['status']}")
        print(f"    - Feasible suppliers: {len(tender['feasible_suppliers'])}")
        print(f"    - Feasible IDs: {tender['feasible_suppliers']}")

        # Check feasible set
        print(f"    - Excluded suppliers: {tender.get('excluded_suppliers_with_reasons', [])}")
        assert len(tender["feasible_suppliers"]) == 2, f"Expected 2 feasible suppliers, got {len(tender['feasible_suppliers'])}"
        assert (
            supplier1["supplier_id"] in tender["feasible_suppliers"]
        ), "Supplier1 should be feasible"
        assert (
            supplier2["supplier_id"] in tender["feasible_suppliers"]
        ), "Supplier2 should be feasible"
        assert (
            supplier3["supplier_id"] not in tender["feasible_suppliers"]
        ), "Supplier3 should be excluded (no ISO27001)"
        print(f"    ✓ Binary matching correct: 2 feasible, 1 excluded")

        # Step 6: Select supplier (constitutional selection)
        print("\n🎲 Step 6: Select supplier (constitutional mechanism)...")
        tender = ftl.select_supplier(
            tender["tender_id"],
            selection_seed="test-seed-12345",  # Deterministic for testing
        )
        print(f"  ✓ Selected supplier")
        print(f"    - Selected: {tender['selected_supplier_id']}")
        print(f"    - Reason: {tender.get('selection_reason', 'N/A')}")

        # Verify selection is from feasible set
        assert (
            tender["selected_supplier_id"] in tender["feasible_suppliers"]
        ), "Selected supplier must be in feasible set"
        print(f"    ✓ Selection valid (from feasible set)")

        # Step 7: Award tender
        print("\n🏆 Step 7: Award tender with contract terms...")
        tender = ftl.award_tender(
            tender_id=tender["tender_id"],
            contract_value=Decimal("480000"),
            contract_terms={
                "delivery_deadline": "2025-12-31",
                "payment_schedule": "30% upfront, 70% on delivery",
                "penalties": {"late_delivery_per_day": 1000},
            },
        )
        print(f"  ✓ Awarded tender")
        print(f"    - Status: {tender['status']}")
        print(f"    - Contract value: ${tender.get('contract_value', 'N/A')}")

        # Check supplier's total_value_awarded was updated
        selected_supplier = ftl.supplier_registry.get(tender["selected_supplier_id"])
        assert (
            selected_supplier["total_value_awarded"] == Decimal("480000")
        ), "Supplier value should be updated"
        print(f"    ✓ Supplier total_value_awarded updated")

        # Step 8: Complete tender (reputation update)
        print("\n✅ Step 8: Complete tender with quality assessment...")
        initial_reputation = selected_supplier["reputation_score"]
        print(f"    - Initial reputation: {initial_reputation:.2f}")

        tender = ftl.complete_tender(
            tender_id=tender["tender_id"],
            completion_report={
                "tests_passed": ["security_audit", "load_test", "uptime_test"],
                "delivery_date": "2025-11-15",
                "customer_satisfaction": 4.8,
            },
            final_quality_score=0.95,  # Excellent delivery
        )
        print(f"  ✓ Completed tender")
        print(f"    - Status: {tender['status']}")
        print(f"    - Quality score: {tender.get('final_quality_score', 'N/A')}")

        # Check reputation was updated
        selected_supplier = ftl.supplier_registry.get(tender["selected_supplier_id"])
        new_reputation = selected_supplier["reputation_score"]
        print(f"    - New reputation: {new_reputation:.2f}")
        assert (
            new_reputation > initial_reputation
        ), "Reputation should increase with good quality"
        print(f"    ✓ Reputation updated (increased by {new_reputation - initial_reputation:.2f})")

        # Step 9: Run tick (check triggers)
        print("\n⏰ Step 9: Run tick loop (check procurement triggers)...")
        tick_result = ftl.tick()
        print(f"  ✓ Tick completed")
        print(f"    - Risk level: {tick_result.freedom_health.risk_level}")
        print(f"    - Triggered events: {len(tick_result.triggered_events)}")
        print(f"    - Warnings: {tick_result.has_warnings()}")
        print(f"    - Halts: {tick_result.has_halts()}")

        # Step 10: Verify complete workflow
        print("\n✨ Step 10: Verify complete workflow...")

        # Check all suppliers exist
        all_suppliers = ftl.list_suppliers()
        assert len(all_suppliers) == 3, "Should have 3 suppliers"
        print(f"  ✓ All suppliers registered: {len(all_suppliers)}")

        # Check tender exists and is completed
        all_tenders = ftl.list_tenders()
        assert len(all_tenders) == 1, "Should have 1 tender"
        assert all_tenders[0]["status"] == "COMPLETED", "Tender should be completed"
        print(f"  ✓ Tender completed successfully")

        # Check event log has all events
        all_events = ftl.event_store.load_all_events()
        event_types = [e.event_type for e in all_events]
        print(f"  ✓ Total events logged: {len(all_events)}")

        # Verify key events exist
        assert "SupplierRegistered" in event_types, "Should have supplier registration"
        assert (
            "CapabilityClaimAdded" in event_types
        ), "Should have capability claims"
        assert "TenderCreated" in event_types, "Should have tender creation"
        assert (
            "FeasibleSetComputed" in event_types
        ), "Should have feasible set computation"
        assert "SupplierSelected" in event_types, "Should have supplier selection"
        assert "TenderAwarded" in event_types, "Should have tender award"
        assert "TenderCompleted" in event_types, "Should have tender completion"
        assert "ReputationUpdated" in event_types, "Should have reputation update"
        print(f"  ✓ All key events present in event log")

        # Print summary
        print("\n" + "=" * 70)
        print("🎉 SUCCESS! Full procurement workflow verified!")
        print("=" * 70)
        print("\n📊 Summary:")
        print(f"  - Suppliers registered: 3")
        print(f"  - Capabilities added: 4")
        print(f"  - Tenders created: 1")
        print(f"  - Feasible set size: 2 (binary matching worked)")
        print(f"  - Supplier selected: ✓ (constitutional selection)")
        print(f"  - Tender awarded: ✓ (${tender.get('contract_value', 'N/A')})")
        print(f"  - Tender completed: ✓ (quality score: {tender.get('final_quality_score', 'N/A')})")
        print(f"  - Reputation updated: ✓ (new score: {new_reputation:.2f})")
        print(f"  - Total events logged: {len(all_events)}")
        print("\n✅ All assertions passed!")
        print("✅ Event sourcing working correctly!")
        print("✅ Binary matching working correctly!")
        print("✅ Constitutional selection working correctly!")
        print("✅ Reputation updates working correctly!")
        print("✅ v0.3 Resource & Procurement Module: OPERATIONAL! 🚀")
        print("=" * 70)

        return True


if __name__ == "__main__":
    try:
        test_full_procurement_workflow()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
