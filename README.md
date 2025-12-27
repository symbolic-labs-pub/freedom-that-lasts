# Freedom That Lasts

**Event-sourced governance kernel preserving future option space through revocable delegation, time-bound laws, and anti-tyranny safeguards.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

Freedom That Lasts is a Python package implementing the governance concepts from the book "Freedom That Lasts" as deterministic, auditable code. It demonstrates that freedom can be structurally stable, not just aspirational.

**Core Philosophy**: Minimal code that fully expresses the theory. Every line implements an anti-tyranny safeguard.

## Key Features

### Governance & Delegation
- **Event Sourcing**: Append-only event log as source of truth
- **Idempotency**: Same command = same result (deterministic replay)
- **Revocable Delegation**: Authority with TTL and automatic expiry
- **Time-Bound Laws**: Mandatory review checkpoints prevent drift
- **Anti-Tyranny Safeguards**: Concentration metrics, automatic warnings/halts
- **Privacy-by-Default**: Aggregate transparency without individual coercion
- **FreedomHealth Scorecard**: Real-time risk monitoring (GREEN/YELLOW/RED)

### Budget Module (v0.2)
- **Law-Scoped Budgets**: Each budget tied to a specific law
- **Flex Classes**: CRITICAL (5%), IMPORTANT (15%), ASPIRATIONAL (50%) step-size limits
- **Multi-Gate Enforcement**: 4 independent validation gates (step-size, balance, authority, limits)
- **Zero-Sum Constraint**: Strict balancing prevents unauthorized budget growth
- **Complete Audit Trail**: Every adjustment and expenditure logged as immutable event
- **Automatic Triggers**: Balance violations and overspending detected automatically
- **Graduated Constraints**: Large cuts require many small steps (anti-manipulation)

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

# Create budget with flex classes (v0.2)
budget = ftl.create_budget(
    law_id=law["law_id"],
    fiscal_year=2025,
    items=[
        {
            "name": "Staff Salaries",
            "allocated_amount": "500000",
            "flex_class": "CRITICAL",      # 5% max change
            "category": "personnel"
        },
        {
            "name": "Equipment",
            "allocated_amount": "200000",
            "flex_class": "IMPORTANT",     # 15% max change
            "category": "capital"
        }
    ]
)

# Activate budget & adjust allocation (zero-sum)
ftl.activate_budget(budget["budget_id"])
ftl.adjust_allocation(
    budget_id=budget["budget_id"],
    adjustments=[
        {"item_id": "item-1", "change_amount": Decimal("-25000")},  # -5% (within CRITICAL limit)
        {"item_id": "item-2", "change_amount": Decimal("25000")},   # +12.5% (within IMPORTANT limit)
    ],
    reason="Reallocate for new equipment"
)

# Approve expenditure
ftl.approve_expenditure(
    budget_id=budget["budget_id"],
    item_id="item-1",
    amount=50000,
    purpose="Hire data analyst"
)
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

# Budget management (v0.2)
ftl budget create --law-id <id> --fiscal-year 2025 --items '[
  {"name":"Staff","allocated_amount":"500000","flex_class":"CRITICAL","category":"personnel"}
]'
ftl budget activate --id <budget_id>
ftl budget show --id <budget_id>
ftl budget adjust --id <id> --adjustments '[...]' --reason "Reallocate funds"

# Expenditure tracking
ftl expenditure approve --budget <id> --item <id> --amount 50000 --purpose "Hire analyst"
ftl expenditure list --budget <id>
```

## Installation

```bash
# From source
git clone https://github.com/freedom-that-lasts/freedom-that-lasts
cd freedom-that-lasts
pip install -e ".[dev]"

# Run tests
pytest

# Run examples
python examples/city_pilot.py       # Law & delegation example
python examples/budget_example.py   # Budget module examples (v0.2)
```

## Current Status: v0.2 COMPLETE

### ✅ v0.1: Governance Kernel (Weeks 1-8)
- **Kernel**: Event store (SQLite), projection store, IDs (UUIDv7), time abstraction, SafetyPolicy
- **Law Module**: Workspace management, delegation DAG with TTL/expiry, law lifecycle (DRAFT→ACTIVE→REVIEW→SUNSET)
- **Safeguards**: Delegation concentration metrics (Gini), FreedomHealth scorecard, reflex triggers
- **Tick Engine**: Automatic safeguard evaluation with warnings/halts
- **FTL Façade**: High-level Python API hiding event sourcing complexity
- **CLI**: Complete typer-based CLI (init, workspace, delegate, law, tick, health, safety)
- **Documentation**: ARCHITECTURE.md, THREAT_MODEL.md
- **Examples**: city_pilot.py, replay_demo.py
- **Tests**: 76 tests, 72% coverage

### ✅ v0.2: Budget Module (4 Weeks)
- **Budget Aggregate**: Law-scoped budgets with flex classes (CRITICAL/IMPORTANT/ASPIRATIONAL)
- **Multi-Gate Enforcement**: Step-size (5%/15%/50%), balance (zero-sum), authority, limits
- **Commands & Events**: CreateBudget, ActivateBudget, AdjustAllocation, ApproveExpenditure, CloseBudget
- **Projections**: BudgetRegistry, ExpenditureLog, BudgetHealthProjection
- **Triggers**: Budget balance violations, expenditure overspending (integrated with TickEngine)
- **SafetyPolicy**: Budget thresholds (step-size limits, balance enforcement, concentration)
- **CLI**: 8 budget/expenditure commands (create, activate, adjust, show, list, close, approve, list)
- **Documentation**: ARCHITECTURE.md updated with budget module design
- **Examples**: budget_example.py (5 comprehensive scenarios)
- **Tests**: 22 budget tests (invariants, handlers, projections, triggers, integration, CLI)
- **Coverage**: 87% invariants, 87% handlers, 83% projections, 100% triggers

**Roadmap:**
- v0.3 (4 weeks): Resource/Procurement module
- v1.0 (4 weeks): Stabilization, security audit

## Architecture

```
Event Sourcing Foundation
├── Events (immutable facts)
├── Commands (intentions)
├── Projections (read models)
└── Triggers (automatic reflexes)

Domain Modules
├── Law (delegation, lifecycle, checkpoints) [v0.1]
├── Budget (flex classes, multi-gate enforcement) [v0.2]
├── Feedback (FreedomHealth, triggers) [v0.1]
└── CLI (user interface) [v0.1+v0.2]

Anti-Tyranny Safeguards
├── Delegation TTL (max 365 days)
├── Concentration metrics (Gini warnings)
├── Checkpoint enforcement (mandatory review)
├── Privacy-by-default (aggregate transparency)
├── Budget flex classes (graduated constraints) [v0.2]
├── Zero-sum balancing (prevent budget growth) [v0.2]
└── Multi-gate validation (defense in depth) [v0.2]
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

- [ARCHITECTURE.md](ARCHITECTURE.md) - Event sourcing design, budget module architecture, and technical details
- [THREAT_MODEL.md](THREAT_MODEL.md) - Anti-tyranny safeguards and threat analysis
- [Examples](examples/) - Working code examples:
  - `city_pilot.py` - Law lifecycle and delegation example
  - `replay_demo.py` - Event sourcing demonstration
  - `budget_example.py` - Budget module comprehensive examples (5 scenarios)

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
