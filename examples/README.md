# Examples

This directory contains working examples demonstrating Freedom That Lasts governance system.

## Available Examples

### 1. City Pilot (`city_pilot.py`)

**Realistic governance scenario**: Budapest health department implementing a primary care pilot program

**Demonstrates**:
- Workspace hierarchy creation
- Delegation with time-to-live (TTL)
- Law creation with mandatory review checkpoints
- Law activation and lifecycle
- Automatic safeguard triggers (concentration detection)
- Health monitoring (FreedomHealth scorecard)
- Review completion
- Safety event logging

**Run**:
```bash
python examples/city_pilot.py
```

**Expected output**:
- Step-by-step governance workflow
- Health status after each phase
- Demonstration of checkpoint review
- Concentration metrics
- Complete audit trail

**Duration**: ~10 seconds

### 2. Replay Demo (`replay_demo.py`)

**Event sourcing demonstration**: Deterministic state reconstruction from events

**Demonstrates**:
- Event store as source of truth
- Projection rebuilding
- Deterministic replay (same events → same state)
- Event-by-event inspection
- Debugging use case (find when law activated)
- Complete audit trail

**Run**:
```bash
python examples/replay_demo.py
```

**Expected output**:
- Initial state creation
- State capture
- Projection rebuild
- State comparison (should be identical)
- Event-by-event replay walkthrough
- Audit trail inspection

**Duration**: ~5 seconds

## Key Concepts Illustrated

### Event Sourcing
Both examples demonstrate that **events are the source of truth**:
- All state changes captured as immutable events
- Current state is derived by replaying events
- Projections are materialized views (can be rebuilt)

### Anti-Tyranny Safeguards
`city_pilot.py` shows how safeguards are automatic:
- Delegation concentration detected via Gini coefficient
- Law checkpoints enforced by tick loop
- TTL limits prevent permanent authority
- Health scorecard surfaces risk

### Determinism
`replay_demo.py` proves:
- Same events in same order → identical state
- Projections can be dropped and rebuilt
- Perfect auditability (no state hidden)

## Running All Examples

```bash
# Run from project root
python examples/city_pilot.py
python examples/replay_demo.py
```

## Using as Templates

These examples can be adapted for:

**Local Government**: City councils, district management
**Corporate Governance**: Board decisions, delegation chains
**Research Organizations**: Lab policies, equipment access
**Open Source Projects**: RFC-style governance, voting systems

## Next Steps

After running examples:

1. **Explore the database**:
   ```bash
   # Run city_pilot.py and note the database path
   sqlite3 /tmp/tmp*.db
   SELECT event_type, occurred_at, actor_id FROM events;
   ```

2. **Try the CLI**:
   ```bash
   ftl init --db governance.db
   ftl workspace create --name "Test"
   ftl health
   ```

3. **Read the docs**:
   - [ARCHITECTURE.md](../ARCHITECTURE.md) - Event sourcing design
   - [THREAT_MODEL.md](../THREAT_MODEL.md) - Anti-tyranny safeguards

4. **Write your own scenario**:
   ```python
   from freedom_that_lasts import FTL

   ftl = FTL("my_scenario.db")
   # Your governance logic here
   ```

## Troubleshooting

**Import errors**: Ensure package is installed
```bash
pip install -e .
```

**Database errors**: Examples use temporary databases, no cleanup needed

**Time-related issues**: Examples use TestTimeProvider for determinism (not real time)

## License

These examples are part of Freedom That Lasts and use the same Apache 2.0 license.
