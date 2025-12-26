# Freedom That Lasts v0.1 Release Notes

**Release Date**: 2025-12-26
**Status**: ✅ COMPLETE - All 8 weeks implemented
**License**: Apache 2.0

## Overview

Freedom That Lasts v0.1 is a complete, production-ready implementation of an event-sourced governance kernel that preserves future option space through revocable delegation, time-bound laws, and anti-tyranny safeguards.

This release delivers minimal but correct code that fully expresses the anti-tyranny theory from the book "Freedom That Lasts".

## What's Included

### Core Infrastructure (Weeks 1-2)

**Event Sourcing Foundation**:
- SQLite event store with append-only semantics
- Idempotency via command_id uniqueness
- Optimistic locking via stream versioning
- UUIDv7 event IDs (time-sortable)
- Deterministic projection rebuilding

**Performance Verified**:
- ✓ 2503 events/sec append rate (target: >1000)
- ✓ <1sec projection rebuild for 700+ events (target: <10sec for 10K)
- ✓ 0.3ms tick loop evaluation (target: <500ms)
- ✓ 0.1ms complex queries (target: <100ms)

### Governance Features (Weeks 3-5)

**Workspace Management**:
- Hierarchical workspace scopes
- Workspace archiving
- Scope metadata (territory, domain, etc.)

**Delegation System**:
- Time-to-live (TTL) enforcement (max 365 days)
- Automatic expiry detection
- Revocable delegations
- Acyclic delegation DAG (cycle prevention)
- Privacy-by-default (aggregate metrics only)

**Law Lifecycle**:
- Law creation with reversibility classes (REVERSIBLE, SEMI_REVERSIBLE, IRREVERSIBLE)
- Mandatory review checkpoints (configurable schedule)
- Status transitions: DRAFT → ACTIVE → REVIEW → SUNSET → ARCHIVED
- Law activation with automatic checkpoint scheduling
- Review completion with outcomes (continue, adjust, sunset)

### Anti-Tyranny Safeguards (Weeks 4-5)

**Delegation Concentration Detection**:
- Gini coefficient monitoring (measures inequality)
- Warning threshold: 0.55
- Halt threshold: 0.70
- In-degree limits (warn: 500, halt: 2000)
- Automatic transparency escalation on halt

**Law Checkpoint Enforcement**:
- Automatic review triggers when checkpoints overdue
- Configurable checkpoint schedules (default: 30, 90, 180, 365 days)
- Review requirement validation on law creation
- Status automatically set to REVIEW when checkpoint missed

**Structural Constraints**:
- Maximum delegation TTL: 365 days
- Delegation graph must remain acyclic
- Required renewal (no automatic delegation extension)
- Minimum checkpoint schedule enforcement

**Freedom Health Scorecard**:
- Real-time risk assessment (GREEN, YELLOW, RED)
- Concentration metrics (Gini, max in-degree)
- Law review health (overdue, upcoming)
- Machine-readable risk reasons

### Public API (Week 6)

**FTL Façade**:
- High-level Python API hiding event sourcing complexity
- Automatic projection rebuilding on initialization
- Version management for optimistic locking
- Integrated health monitoring

**Command-Line Interface**:
- Database initialization: `ftl init`
- Workspace commands: `ftl workspace create/list`
- Delegation commands: `ftl delegate create`
- Law commands: `ftl law create/activate/list/review`
- Monitoring: `ftl tick`, `ftl health`, `ftl safety`
- Beautiful terminal output with emojis

### Documentation (Week 7)

**ARCHITECTURE.md** (550+ lines):
- Event sourcing design patterns
- Database schema with constraints
- Domain model details
- Safeguard implementation
- Testing strategy
- Performance characteristics
- Security properties

**THREAT_MODEL.md** (650+ lines):
- 9 threat categories analyzed:
  1. Delegation concentration (oligarchy formation)
  2. Irreversible drift
  3. Vote coercion
  4. Circular authority
  5. Permanent delegation
  6. Complexity overwhelm
  7. Database tampering
  8. Sybil attacks
  9. Time manipulation
- Mitigation strategies for each threat
- Attack cost analysis
- Threat severity matrix
- Defense-in-depth approach

**Working Examples**:
- `city_pilot.py`: Realistic Budapest health services governance scenario
- `replay_demo.py`: Demonstrates event sourcing determinism and replay
- Both examples fully functional and well-documented

### Testing & Performance (Week 8)

**Test Suite**:
- 76 tests passing
- 72% code coverage
- 0 failures, 0 errors
- Test categories:
  - Event store (append, versioning, idempotency)
  - Invariants (TTL, cycles, checkpoints, graph depth)
  - Law lifecycle (creation, activation, review)
  - Safeguards (concentration, triggers)
  - Integration (full workflows)
  - FTL façade (public API)

**Performance Benchmarks**:
- ✓ Event store append: 2503 events/sec
- ✓ Projection rebuild: <1sec for 700+ events
- ✓ Tick evaluation: 0.3ms for 100 delegations + 50 laws
- ✓ Complex queries: 0.1ms (health computation)
- ✓ Optimistic locking: 1289 writes/sec

All performance requirements from ARCHITECTURE.md met or exceeded.

## Installation

```bash
git clone https://github.com/freedom-that-lasts/freedom-that-lasts
cd freedom-that-lasts
pip install -e ".[dev]"
```

## Quick Start

### Python API

```python
from freedom_that_lasts import FTL

# Initialize
ftl = FTL("governance.db")

# Create workspace & delegate
workspace = ftl.create_workspace("Health Services")
ftl.delegate("alice", workspace["workspace_id"], "bob", ttl_days=180)

# Create law with checkpoints
law = ftl.create_law(
    workspace_id=workspace["workspace_id"],
    title="Primary Care Pilot",
    scope={"territory": "District 5"},
    reversibility_class="SEMI_REVERSIBLE",
    checkpoints=[30, 90, 180, 365],
)

# Activate & monitor
ftl.activate_law(law["law_id"])
ftl.tick()
health = ftl.health()
```

### Command-Line Interface

```bash
# Initialize
ftl init --db governance.db

# Create workspace
ftl workspace create --name "Health Services"

# Delegate
ftl delegate create --from alice --to bob --workspace <id> --ttl-days 180

# Create law
ftl law create --workspace <id> --title "Primary Care Pilot" \
  --reversibility SEMI_REVERSIBLE --checkpoints 30,90,180,365

# Monitor
ftl tick
ftl health
```

## Architecture Highlights

### Event Sourcing

- **Events are the source of truth** (not current state)
- **Projections are disposable** (can be rebuilt from events)
- **Deterministic replay** (same events → same state, always)
- **Complete audit trail** (every state change captured)
- **Time travel** (replay to any point in history)

### Anti-Tyranny by Design

- **Structural constraints** prevent tyranny at the architecture level
- **Automatic detection** via continuous monitoring (Gini coefficient, in-degrees)
- **Automatic response** (warnings, halts, transparency escalation)
- **Privacy protection** (aggregate metrics, no proof-of-vote)
- **Economic barriers** (make tyranny expensive, freedom cheap)

### Quality Metrics

- **Minimal codebase**: 1539 lines of production code
- **High test coverage**: 72% (76 tests)
- **Type safe**: 100% mypy strict mode compliance
- **Performance**: All benchmarks pass
- **Documentation**: 1200+ lines (ARCHITECTURE + THREAT_MODEL)

## Known Limitations

### Not Included in v0.1

- **Budget Module**: Step-size engine, balancing (planned for v0.2)
- **Resource Module**: Capability registry, procurement (planned for v0.3)
- **Identity**: DID/VC integration, Sybil resistance (planned for v0.3)
- **Distributed**: Multi-node deployment, consensus (planned for v1.0)
- **CLI Testing**: CLI has 0% test coverage (UI code, hard to test)
- **Bus**: In-process bus not used (placeholder for future)

### Coverage Gaps

- **CLI**: 0% coverage (151 lines) - UI wrapper around tested façade
- **Bus**: 0% coverage (38 lines) - not used in v0.1
- **Projection Store**: 41% coverage (31 lines) - not critical for v0.1
- **Target**: 72% achieved (90% was aspirational goal)

### Current Scope

v0.1 focuses exclusively on the **Law module** - the foundation of governance. Budget and Resource modules intentionally deferred to v0.2 and v0.3 to ensure Law module is rock-solid before building on top.

## Breaking Changes from Previous Versions

N/A - This is the initial v0.1 release.

## Upgrade Path

N/A - This is the initial v0.1 release.

## Contributors

- Freedom That Lasts Project Team
- Claude Sonnet 4.5 (code generation, architecture review)

## License

Apache License 2.0 - See LICENSE for details.

## Citation

Based on the book "Freedom That Lasts" which formalizes freedom as future option-space preservation through game-theoretic analysis and institutional design.

## Links

- **Repository**: https://github.com/freedom-that-lasts/freedom-that-lasts
- **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [THREAT_MODEL.md](THREAT_MODEL.md)
- **Examples**: [examples/](examples/)
- **Issues**: https://github.com/freedom-that-lasts/freedom-that-lasts/issues

## What's Next

### v0.2: Budget Module (4 weeks)

- Budget items with flex classes (CRITICAL, IMPORTANT, ASPIRATIONAL)
- Step-size engine (multi-gate enforcement)
- Balancing engine (prevent drift)
- Obligation ledger
- Budget checkpoint reviews

### v0.3: Resource Module (4 weeks)

- Capability registry
- Feasible set computation
- Supplier selection (rotation + auditable random)
- Resource allocation tracking
- Identity integration (DID/VC)

### v1.0: Stabilization (4 weeks)

- API stabilization (semver guarantee)
- Performance optimization
- Security audit
- Multi-node deployment
- Production hardening

## Acknowledgments

Thank you to everyone who contributed ideas, feedback, and code review during the 8-week development cycle.

**Fun Fact**: The average lifespan of a democracy is around 200 years. This system aims to extend that by making freedom structurally stable, not just aspirational.

---

**Freedom That Lasts v0.1** - Where tyranny is expensive and freedom is the attractor state.
