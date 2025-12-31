# Examples

This directory contains working examples demonstrating Freedom That Lasts governance system.

## Available Examples

### 1. City Pilot (`city_pilot.py`)

**Realistic governance scenario**: Albuquerque health department implementing a primary care pilot program

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

### 3. Budget Example (`budget_example.py`)

**Budget module demonstration**: Law-scoped budgets with multi-gate enforcement (v0.2)

**Demonstrates**:
- Budget creation with flex classes (CRITICAL/IMPORTANT/ASPIRATIONAL)
- Multi-gate enforcement (step-size, balance, authority, limits)
- Zero-sum allocation adjustments
- Expenditure approval and tracking
- Budget triggers (balance violations, overspending)
- Complete audit trail for financial transparency

**Run**:
```bash
python examples/budget_example.py
```

**Expected output**:
- 5 comprehensive budget scenarios
- Flex step-size enforcement (5%/15%/50% limits)
- Zero-sum constraint validation
- Expenditure tracking
- Trigger detection
- Budget health monitoring

**Duration**: ~15 seconds

### 4. Procurement Example (`procurement_example.py`)

**Resource module demonstration**: Constitutional supplier selection mechanisms (v0.3)

**Demonstrates**:
- Algorithmic supplier selection (rotation, random, hybrid)
- Feasibility constraints (capacity, certification, experience, reputation)
- Deterministic seed-based randomness (SHA-256)
- Supplier concentration monitoring (Gini coefficient)
- Complete procurement audit trail
- Anti-capture safeguards

**Run**:
```bash
python examples/procurement_example.py
```

**Expected output**:
- Rotation selection (load balancing)
- Random selection (fairness with reproducibility)
- Hybrid selection (rotation + random)
- Feasibility filtering
- Gini coefficient calculation
- Supplier share tracking

**Duration**: ~10 seconds

## Key Concepts Illustrated

### Event Sourcing
Both examples demonstrate that **events are the source of truth**:
- All state changes captured as immutable events
- Current state is derived by replaying events
- Projections are materialized views (can be rebuilt)

### Anti-Tyranny Safeguards
Multiple examples show how safeguards are automatic:
- **Delegation**: Concentration detected via Gini coefficient (`city_pilot.py`)
- **Laws**: Checkpoints enforced by tick loop (`city_pilot.py`)
- **Budget**: Multi-gate enforcement prevents manipulation (`budget_example.py`)
- **Procurement**: Algorithmic selection prevents favoritism (`procurement_example.py`)
- **TTL**: Limits prevent permanent authority (all examples)
- **Health**: Scorecard surfaces risk (all examples)

### Determinism
`replay_demo.py` proves:
- Same events in same order → identical state
- Projections can be dropped and rebuilt
- Perfect auditability (no state hidden)

### Multi-Gate Enforcement
`budget_example.py` demonstrates defense in depth:
- **Gate 1**: Flex step-size limits (5%/15%/50%)
- **Gate 2**: Zero-sum balance constraint
- **Gate 3**: Delegation authority validation
- **Gate 4**: No overspending constraint
- **Result**: 4 independent checks prevent budget manipulation

### Constitutional Procurement
`procurement_example.py` shows algorithmic fairness:
- **Rotation**: Load-balancing prevents monopolies
- **Random**: Cryptographic seed-based selection
- **Hybrid**: Rotation among low-loaded, then random
- **Feasibility**: Hard pass/fail gates (no ranking)
- **Transparency**: Full audit trail with reproducibility

## Running All Examples

```bash
# Run from project root
python examples/city_pilot.py        # Law & delegation (v0.1)
python examples/replay_demo.py       # Event sourcing (v0.1)
python examples/budget_example.py    # Budget module (v0.2)
python examples/procurement_example.py  # Resources module (v0.3)
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
   - [ARCHITECTURE.md](../docs/ARCHITECTURE.md) - Event sourcing design
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
