#!/usr/bin/env python3
"""
Event Replay Demonstration - Deterministic State Reconstruction

This example demonstrates one of the core properties of event sourcing:
the ability to deterministically rebuild system state by replaying events.

Key Concepts:
1. Events are the source of truth (not current state)
2. Projections (read models) are materialized views of events
3. Projections can be dropped and rebuilt identically
4. Same events in same order → identical state (determinism)
5. Replay enables debugging, auditing, and state migration

Scenario:
- Create some governance events (workspace, delegation, law)
- Capture projection state
- Drop all projections
- Rebuild from events
- Verify state is identical

Run:
    python examples/replay_demo.py
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from freedom_that_lasts import FTL
from freedom_that_lasts.kernel.time import TestTimeProvider


def print_section(title: str) -> None:
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def serialize_state(ftl: FTL) -> dict:
    """Capture current projection state for comparison"""
    return {
        "workspaces": ftl.workspace_registry.to_dict(),
        "laws": {law_id: law for law_id, law in ftl.law_registry.laws.items()},
        "delegations": {
            del_id: delegation
            for del_id, delegation in ftl.delegation_graph.delegations.items()
        },
    }


def states_equal(state1: dict, state2: dict) -> bool:
    """Compare two states for equality"""
    # Convert to JSON strings for comparison (handles datetime serialization)
    json1 = json.dumps(state1, sort_keys=True, default=str)
    json2 = json.dumps(state2, sort_keys=True, default=str)
    return json1 == json2


def main() -> None:
    """Run replay demonstration"""

    print_section("Event Replay Demonstration - Deterministic Rebuilds")

    # Create temporary database
    db_path = Path(tempfile.mktemp(suffix=".db"))

    # Use test time provider for determinism
    fixed_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    time_provider = TestTimeProvider(fixed_time)

    print(f"Database: {db_path}")
    print(f"Fixed time: {fixed_time.isoformat()}")
    print(f"\nThis demo will:")
    print("  1. Create governance events")
    print("  2. Capture projection state")
    print("  3. Drop and rebuild projections")
    print("  4. Verify identical state")

    # Phase 1: Create initial events
    print_section("Phase 1: Create Initial Events")

    print("Initializing FTL and creating governance structures...")
    ftl1 = FTL(str(db_path), time_provider=time_provider)

    # Create workspace
    workspace = ftl1.create_workspace(
        name="Research Department", scope={"domain": "research"}
    )
    print(f"✓ Created workspace: {workspace['name']}")

    # Create delegations
    delegation1 = ftl1.delegate(
        from_actor="director_alice",
        workspace_id=workspace["workspace_id"],
        to_actor="team_lead_bob",
        ttl_days=180,
    )
    print(f"✓ Created delegation: director_alice → team_lead_bob")

    delegation2 = ftl1.delegate(
        from_actor="director_alice",
        workspace_id=workspace["workspace_id"],
        to_actor="team_lead_carol",
        ttl_days=180,
    )
    print(f"✓ Created delegation: director_alice → team_lead_carol")

    # Create law
    law = ftl1.create_law(
        workspace_id=workspace["workspace_id"],
        title="Data Sharing Policy",
        scope={"territory": "All departments"},
        reversibility_class="REVERSIBLE",
        checkpoints=[30, 90, 180, 365],
    )
    print(f"✓ Created law: {law['title']}")

    # Activate law
    ftl1.activate_law(law["law_id"])
    print(f"✓ Activated law")

    # Run tick
    ftl1.tick()
    print(f"✓ Ran tick loop")

    # Phase 2: Capture state
    print_section("Phase 2: Capture Projection State")

    state1 = serialize_state(ftl1)

    print("Captured state snapshot:")
    print(f"  Workspaces: {len(state1['workspaces']['workspaces'])}")
    print(f"  Delegations: {len(state1['delegations'])}")
    print(f"  Laws: {len(state1['laws'])}")

    # Get event count
    all_events = ftl1.event_store.load_all_events()
    print(f"\n  Total events in store: {len(all_events)}")

    print("\nEvent types:")
    event_types = {}
    for event in all_events:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

    for event_type, count in sorted(event_types.items()):
        print(f"    {event_type}: {count}")

    # Phase 3: Create new instance (simulates projection rebuild)
    print_section("Phase 3: Rebuild State from Events")

    print("Creating new FTL instance with same database...")
    print("This triggers automatic projection rebuild from events...")

    # New instance - will rebuild projections from event store
    ftl2 = FTL(str(db_path), time_provider=time_provider)

    state2 = serialize_state(ftl2)

    print("\n✓ Projections rebuilt from events")
    print(f"  Workspaces: {len(state2['workspaces']['workspaces'])}")
    print(f"  Delegations: {len(state2['delegations'])}")
    print(f"  Laws: {len(state2['laws'])}")

    # Phase 4: Verify determinism
    print_section("Phase 4: Verify Deterministic Replay")

    print("Comparing original state vs rebuilt state...")

    if states_equal(state1, state2):
        print("\n✓✓✓ SUCCESS: States are IDENTICAL")
        print("\nDeterministic replay verified!")
        print("Same events → Same state (always)")
    else:
        print("\n✗✗✗ FAILURE: States differ!")
        print("\nThis should never happen with correct event sourcing.")

        # Show differences
        print("\nDifferences:")
        for key in ["workspaces", "delegations", "laws"]:
            if state1[key] != state2[key]:
                print(f"  {key}: DIFFERENT")
            else:
                print(f"  {key}: identical")

    # Phase 5: Demonstrate replay with inspection
    print_section("Phase 5: Event-by-Event Replay Inspection")

    print("Replaying events step-by-step...\n")

    # Create fresh projections
    from freedom_that_lasts.law.projections import (
        DelegationGraph,
        LawRegistry,
        WorkspaceRegistry,
    )

    workspace_registry = WorkspaceRegistry()
    delegation_graph = DelegationGraph()
    law_registry = LawRegistry()

    # Replay each event
    for i, event in enumerate(all_events, 1):
        print(f"Event {i}: {event.event_type}")
        print(f"  Occurred: {event.occurred_at}")
        print(f"  Actor: {event.actor_id}")

        # Apply to projections
        if event.event_type in ["WorkspaceCreated", "WorkspaceArchived"]:
            workspace_registry.apply_event(event)
            print(f"  → Updated workspace registry")
        elif event.event_type in [
            "DecisionRightDelegated",
            "DelegationRevoked",
            "DelegationExpired",
        ]:
            delegation_graph.apply_event(event)
            print(f"  → Updated delegation graph")
        elif event.event_type.startswith("Law"):
            law_registry.apply_event(event)
            print(f"  → Updated law registry")

        print()

    print(f"Replay complete: {len(all_events)} events processed")

    # Phase 6: Demonstrate debugging use case
    print_section("Phase 6: Debugging Use Case - Find When Law Activated")

    print("Use case: When was the 'Data Sharing Policy' law activated?")
    print("\nSearching event log...")

    for event in all_events:
        if (
            event.event_type == "LawActivated"
            and event.payload.get("law_id") == law["law_id"]
        ):
            print(f"\n✓ Found activation event:")
            print(f"  Event ID: {event.event_id}")
            print(f"  Occurred: {event.occurred_at}")
            print(f"  Actor: {event.actor_id}")
            print(f"  Law ID: {event.payload['law_id']}")
            print(f"  Next checkpoint: {event.payload.get('next_checkpoint_at')}")
            break

    # Phase 7: Demonstrate audit trail
    print_section("Phase 7: Audit Trail - Complete History")

    print(f"Complete audit trail for law: {law['law_id']}\n")

    law_events = [e for e in all_events if e.stream_id == law["law_id"]]

    for i, event in enumerate(law_events, 1):
        print(f"{i}. {event.event_type}")
        print(f"   Time: {event.occurred_at}")
        print(f"   Actor: {event.actor_id}")
        print(f"   Command: {event.command_id}")
        print()

    # Summary
    print_section("Summary: Benefits of Event Sourcing")

    print("✓ Complete audit trail (all events preserved)")
    print("✓ Deterministic replay (same events → same state)")
    print("✓ Time travel (replay to any point in history)")
    print("✓ Debugging (trace any state back to events)")
    print("✓ Migration (rebuild projections with new schema)")
    print("✓ Analytics (analyze event patterns)")

    print(f"\nEvent store is the source of truth.")
    print(f"Projections are disposable materialized views.")
    print(f"This is the foundation of Freedom That Lasts' integrity.")

    print("\n" + "="*70)
    print("Replay demonstration complete")
    print("="*70 + "\n")

    print(f"Database: {db_path}")
    print("To explore events directly:")
    print(f"  sqlite3 {db_path}")
    print(f"  SELECT event_type, occurred_at FROM events;")


if __name__ == "__main__":
    main()
