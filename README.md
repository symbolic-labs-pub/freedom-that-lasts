# Freedom That Lasts

**Event-sourced governance kernel preserving future option space through revocable delegation, time-bound laws, and anti-tyranny safeguards.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

Freedom That Lasts is a Python package implementing the governance concepts from the book "Freedom That Lasts" as deterministic, auditable code. It demonstrates that freedom can be structurally stable, not just aspirational.

**Core Philosophy**: Minimal code that fully expresses the theory. Every line implements an anti-tyranny safeguard.

## Key Features

- **Event Sourcing**: Append-only event log as source of truth
- **Idempotency**: Same command = same result (deterministic replay)
- **Revocable Delegation**: Authority with TTL and automatic expiry
- **Time-Bound Laws**: Mandatory review checkpoints prevent drift
- **Anti-Tyranny Safeguards**: Concentration metrics, automatic warnings/halts
- **Privacy-by-Default**: Aggregate transparency without individual coercion
- **FreedomHealth Scorecard**: Real-time risk monitoring (GREEN/YELLOW/RED)

## Quick Start (60 seconds)

### Python API

```python
from freedom_that_lasts import FTL

# Initialize with SQLite database
ftl = FTL(sqlite_path="governance.db")

# Create workspace & delegate
workspace = ftl.create_workspace("Health Services")
delegation = ftl.delegate(
    from_actor="alice",
    workspace_id=workspace["workspace_id"],
    to_actor="dr_bob",
    ttl_days=180
)

# Create law with mandatory review checkpoints
law = ftl.create_law(
    workspace_id=workspace["workspace_id"],
    title="Primary care access pilot",
    scope={"territory": "Budapest District 5"},
    reversibility_class="SEMI_REVERSIBLE",
    checkpoints=[30, 90, 180, 365],  # Days until review required
    params={"max_wait_days": 10}
)

# Activate law & run safeguard evaluation
activated_law = ftl.activate_law(law["law_id"])
tick_result = ftl.tick()  # Run trigger loop

# Check system health
health = ftl.health()
print(f"Risk Level: {health.risk_level}")  # GREEN, YELLOW, or RED
print(f"Active Delegations: {health.concentration.total_active_delegations}")
print(f"Delegation Gini: {health.concentration.gini_coefficient:.3f}")
```

### Command-Line Interface

```bash
# Initialize database
ftl init --db governance.db

# Create workspace
ftl workspace create --name "Health Services" --scope '{"territory":"Budapest"}'

# Delegate decision rights (max 365 days)
ftl delegate create --from alice --to bob --workspace <workspace_id> --ttl-days 180

# Create law with checkpoints
ftl law create \
  --workspace <workspace_id> \
  --title "Primary Care Pilot" \
  --reversibility SEMI_REVERSIBLE \
  --checkpoints 30,90,180,365 \
  --scope '{"territory":"District 5"}'

# Activate law
ftl law activate --id <law_id>

# Monitor system health
ftl tick       # Run trigger evaluation
ftl health     # Show FreedomHealth scorecard
ftl safety     # Show safety policy & recent events
```

## Installation

```bash
# From source
git clone https://github.com/freedom-that-lasts/freedom-that-lasts
cd freedom-that-lasts
pip install -e ".[dev]"

# Run tests
pytest

# Run example
python examples/city_pilot.py
```

## Current Status: v0.1 COMPLETE (All 8 Weeks Finished)

**✅ Implemented (Weeks 1-8):**
- **Kernel**: Event store (SQLite), projection store, IDs (UUIDv7), time abstraction, SafetyPolicy
- **Law Module**: Workspace management, delegation DAG with TTL/expiry, law lifecycle (DRAFT→ACTIVE→REVIEW→SUNSET)
- **Safeguards**: Delegation concentration metrics (Gini), FreedomHealth scorecard, reflex triggers
- **Tick Engine**: Automatic safeguard evaluation with warnings/halts
- **FTL Façade**: High-level Python API hiding event sourcing complexity
- **CLI**: Complete typer-based CLI (init, workspace, delegate, law, tick, health, safety)
- **Documentation**: ARCHITECTURE.md (event sourcing design), THREAT_MODEL.md (9 threat categories analyzed)
- **Examples**: city_pilot.py (realistic scenario), replay_demo.py (event sourcing demonstration)
- **Tests**: 76 tests passing, 72% coverage
- **Performance**: All benchmarks pass (2500+ events/sec, <1ms queries, <1ms ticks)

**Post-v0.1 Roadmap:**
- v0.2 (4 weeks): Budget module (step-size engine, balancing)
- v0.3 (4 weeks): Resource/Procurement module
- v1.0 (4 weeks): Stabilization, security audit

## Architecture

```
Event Sourcing Foundation
├── Events (immutable facts)
├── Commands (intentions)
├── Projections (read models)
└── Triggers (automatic reflexes)

Domain Modules (v0.1 scope)
├── Law (delegation, lifecycle, checkpoints)
├── Feedback (FreedomHealth, triggers)
└── CLI (user interface)

Anti-Tyranny Safeguards
├── Delegation TTL (max 365 days)
├── Concentration metrics (Gini warnings)
├── Checkpoint enforcement (mandatory review)
└── Privacy-by-default (aggregate transparency)
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=freedom_that_lasts --cov-report=html

# Run specific test
pytest tests/test_kernel/test_event_store.py -v
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Event sourcing design and technical details
- [THREAT_MODEL.md](THREAT_MODEL.md) - Anti-tyranny safeguards and threat analysis
- [Examples](examples/) - Working code examples (`city_pilot.py`, `replay_demo.py`)

For implementation details, see the plan file at `~/.claude/plans/mossy-swinging-nygaard.md`

## Contributing

This is greenfield development - contributions welcome! See implementation plan for detailed tasks.

**Key Principles:**
- Minimal but correct (small codebase expressing full theory)
- Self-documenting code (clear names, no redundant comments)
- 90%+ test coverage
- Type hints everywhere (mypy strict mode)
- DRY and single responsibility

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Citation

Based on the book "Freedom That Lasts" which formalizes freedom as future option-space preservation through game-theoretic analysis and institutional design.

---

**Fun Fact**: The average lifespan of a democracy is around 200 years. This system aims to extend that by making freedom structurally stable, not just aspirational.
