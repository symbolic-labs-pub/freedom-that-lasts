#!/usr/bin/env python3
"""
City Health Services Pilot - Realistic Governance Example

This example demonstrates using Freedom That Lasts for a city health
department implementing a new primary care pilot program.

Scenario:
- Budapest health department wants to pilot improved primary care access
- Pilot covers District 5, 6-month duration
- Authority delegated from Health Commissioner to District Manager
- Law created with mandatory review checkpoints
- System monitors for concentration of power
- Demonstrates full lifecycle: create → delegate → activate → monitor → review

Run:
    python examples/city_pilot.py
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from freedom_that_lasts import FTL
from freedom_that_lasts.feedback.models import RiskLevel
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.models import LawStatus


def print_section(title: str) -> None:
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_health(ftl: FTL) -> None:
    """Print current system health"""
    health = ftl.health()
    risk_emoji = {
        RiskLevel.GREEN: "✓",
        RiskLevel.YELLOW: "⚠️",
        RiskLevel.RED: "🛑",
    }
    emoji = risk_emoji.get(health.risk_level, "?")

    print(f"\nFreedom Health Status: {emoji} {health.risk_level.value}")
    print(f"  Delegation Gini: {health.concentration.gini_coefficient:.3f}")
    print(f"  Max In-Degree: {health.concentration.max_in_degree}")
    print(f"  Active Delegations: {health.concentration.total_active_delegations}")
    print(f"  Active Laws: {health.law_review_health.total_active_laws}")
    print(f"  Overdue Reviews: {health.law_review_health.overdue_reviews}")

    if health.reasons and health.reasons != ["All safeguards within normal bounds"]:
        print("\n  Risk Factors:")
        for reason in health.reasons:
            print(f"    - {reason}")


def main() -> None:
    """Run city health services pilot example"""

    print_section("Budapest Health Services Pilot - Freedom That Lasts")

    # Create temporary database for demo
    db_path = Path(tempfile.mktemp(suffix=".db"))

    # Use test time provider for controlled time progression
    start_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    time_provider = TestTimeProvider(start_time)

    print(f"Initializing governance system...")
    print(f"Database: {db_path}")
    print(f"Start Time: {start_time.isoformat()}")

    ftl = FTL(str(db_path), time_provider=time_provider)

    # Step 1: Create workspace hierarchy
    print_section("Step 1: Create Workspace Hierarchy")

    health_dept = ftl.create_workspace(
        name="Budapest Health Department",
        scope={"territory": "Budapest", "domain": "healthcare"},
    )
    print(f"✓ Created workspace: {health_dept['name']}")
    print(f"  ID: {health_dept['workspace_id']}")

    district5 = ftl.create_workspace(
        name="District 5 Health Services",
        scope={"territory": "Budapest District 5", "domain": "healthcare"},
    )
    print(f"\n✓ Created workspace: {district5['name']}")
    print(f"  ID: {district5['workspace_id']}")

    # Step 2: Delegate authority
    print_section("Step 2: Delegate Decision Authority")

    print("Health Commissioner delegates to District 5 Manager...")
    delegation = ftl.delegate(
        from_actor="commissioner_ana",
        workspace_id=district5["workspace_id"],
        to_actor="manager_peter",
        ttl_days=180,  # 6 months
    )

    print(f"\n✓ Created delegation:")
    print(f"  From: {delegation['from_actor']}")
    print(f"  To: {delegation['to_actor']}")
    print(f"  Workspace: District 5")
    print(f"  TTL: {delegation['ttl_days']} days")
    print(f"  Expires: {delegation['expires_at']}")

    # Step 3: Create law
    print_section("Step 3: Create Primary Care Access Law")

    print("Creating law for primary care pilot...")
    law = ftl.create_law(
        workspace_id=district5["workspace_id"],
        title="Primary Care Access Pilot - District 5",
        scope={
            "territory": "Budapest District 5",
            "valid_days": 180,  # 6-month pilot
            "population_affected": 45000,
        },
        reversibility_class="SEMI_REVERSIBLE",  # Can adjust, but some commitments made
        checkpoints=[30, 90, 180, 365],  # Mandatory review schedule
        params={
            "max_wait_days": 10,  # Patients wait max 10 days for appointment
            "target_clinics": 5,
            "budget_allocated": 500000,  # EUR
        },
        actor_id="manager_peter",
    )

    print(f"\n✓ Created law:")
    print(f"  Title: {law['title']}")
    print(f"  Status: {law['status']}")
    print(f"  Reversibility: {law['reversibility_class']}")
    print(f"  Checkpoints: {law['checkpoints']} days")
    print(f"  Parameters:")
    print(f"    - Max wait: {law['params']['max_wait_days']} days")
    print(f"    - Target clinics: {law['params']['target_clinics']}")
    print(f"    - Budget: €{law['params']['budget_allocated']:,}")

    # Step 4: Activate law
    print_section("Step 4: Activate Law")

    print("Activating law to make it effective...")
    activated_law = ftl.activate_law(law["law_id"], actor_id="manager_peter")

    print(f"\n✓ Law activated:")
    print(f"  Status: {activated_law['status']}")
    print(f"  Activated at: {activated_law['activated_at']}")
    print(f"  Next checkpoint: {activated_law['next_checkpoint_at']}")

    # Step 5: Check initial health
    print_section("Step 5: Initial System Health Check")

    print("Running tick loop to evaluate safeguards...")
    tick_result = ftl.tick()
    print(f"\n✓ Tick completed: {tick_result.tick_id}")
    print(f"  Events triggered: {len(tick_result.triggered_events)}")

    print_health(ftl)

    # Step 6: Fast-forward 35 days (past first checkpoint)
    print_section("Step 6: Time Progression - 35 Days Later")

    print("Advancing time by 35 days...")
    time_provider.advance_days(35)
    new_time = time_provider.now()
    print(f"Current time: {new_time.isoformat()}")

    print("\nRunning tick loop...")
    tick_result = ftl.tick()
    print(f"\n✓ Tick completed")
    print(f"  Events triggered: {len(tick_result.triggered_events)}")

    if tick_result.triggered_events:
        print("\n  Triggered events:")
        for event in tick_result.triggered_events:
            print(f"    - {event.event_type}")
            if event.event_type == "LawReviewTriggered":
                print(f"      Law: {event.payload['law_id']}")
                print(f"      Reason: {event.payload['reason']}")

    print_health(ftl)

    # Check law status
    updated_law = ftl.law_registry.get(law["law_id"])
    print(f"\nLaw status: {updated_law['status']}")
    if updated_law["status"] == "REVIEW":
        print("  ⚠️  Law is now in REVIEW status (checkpoint triggered)")

    # Step 7: Complete review
    print_section("Step 7: Complete Checkpoint Review")

    print("District manager reviews law after 30 days...")
    print("Review finds pilot is successful, continuing with adjustments...")

    reviewed_law = ftl.complete_review(
        law_id=law["law_id"],
        outcome="continue",  # Could be "continue", "adjust", or "sunset"
        notes="30-day review: Pilot showing positive results. Wait times reduced to avg 7 days. Continuing to next checkpoint.",
        actor_id="manager_peter",
    )

    print(f"\n✓ Review completed:")
    print(f"  Outcome: continue")
    print(f"  New status: {reviewed_law['status']}")
    print(f"  Next checkpoint: {reviewed_law.get('next_checkpoint_at')}")

    # Step 8: Add more delegations to demonstrate concentration
    print_section("Step 8: Delegation Concentration Demo")

    print("Adding multiple delegations to demonstrate concentration detection...")

    # Create several more actors delegating to manager_peter
    for i in range(5):
        ftl.delegate(
            from_actor=f"clinic_lead_{i}",
            workspace_id=district5["workspace_id"],
            to_actor="manager_peter",
            ttl_days=90,
        )
        print(f"  ✓ clinic_lead_{i} delegated to manager_peter")

    print("\nRunning tick to check concentration...")
    tick_result = ftl.tick()

    print_health(ftl)

    # Step 9: Query safety events
    print_section("Step 9: Safety Event Log")

    safety_events = ftl.get_safety_events(limit=20)
    print(f"Recent safety events ({len(safety_events)}):")

    for event in safety_events[:10]:  # Show last 10
        print(f"  {event['occurred_at']}: {event['event_type']}")
        if event.get("payload", {}).get("gini_coefficient"):
            print(f"    Gini: {event['payload']['gini_coefficient']:.3f}")

    # Step 10: List all active laws
    print_section("Step 10: Active Laws Summary")

    active_laws = ftl.list_laws(status="ACTIVE")
    print(f"Active laws: {len(active_laws)}")

    for active_law in active_laws:
        print(f"\n  {active_law['title']}")
        print(f"    Status: {active_law['status']}")
        print(f"    Reversibility: {active_law['reversibility_class']}")
        print(f"    Next checkpoint: {active_law.get('next_checkpoint_at')}")

    # Final summary
    print_section("Pilot Summary")

    print("✓ Workspace hierarchy established")
    print("✓ Authority delegated with time limits (180 days)")
    print("✓ Law created with mandatory review checkpoints")
    print("✓ Law activated and first checkpoint review completed")
    print("✓ Concentration monitoring active")
    print("✓ All events logged in immutable audit trail")

    print(f"\nTotal events in system: {len(ftl.event_store.load_all_events())}")

    final_health = ftl.health()
    print(f"\nFinal Risk Level: {final_health.risk_level.value}")

    print("\n" + "="*70)
    print("Governance system operational with anti-tyranny safeguards active")
    print("="*70 + "\n")

    # Cleanup
    print(f"Demo complete. Database at: {db_path}")
    print(f"To explore: ftl init --db {db_path}")


if __name__ == "__main__":
    main()
