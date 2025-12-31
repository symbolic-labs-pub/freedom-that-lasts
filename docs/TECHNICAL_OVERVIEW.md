# Freedom That Lasts

## Buy the book to see the full picture:

[![horizonal_cover.png](press_kit/book/horizonal_cover.png)](https://amazon_book_url)

**Event-sourced governance kernel preserving future option space through revocable delegation, time-bound learning laws, and anti-tyranny safeguards.**

[Buy the book](https://amazon_book_url) to understand the [theory](paper.md) and how is layered!

## Overview

Freedom That Lasts is a Python package implementing the governance concepts from the book "Freedom That Lasts" as deterministic, auditable code. It demonstrates that freedom can be structurally stable, not just aspirational.

**Core Philosophy**: Minimal code that fully expresses the theory.

## Key Features

### Governance & Delegation
- **Event Sourcing**: Append-only event log as source of truth
- **Idempotency**: Same command = same result (deterministic replay)
- **Revocable Delegation**: Authority with TTL and automatic expiry
- **Time-Bound Learning Laws**: Mandatory review checkpoints prevent drift
- **Anti-Tyranny Safeguards**: Concentration metrics, automatic warnings/halts
- **Privacy-by-Default**: Aggregate transparency without individual coercion
- **FreedomHealth Scorecard**: Real-time risk monitoring (GREEN/YELLOW/RED)

### Budget Module
- **Law-Scoped Budgets**: Each budget tied to a specific law
- **Flex Classes**: CRITICAL (5%), IMPORTANT (15%), ASPIRATIONAL (50%) step-size limits
- **Multi-Gate Enforcement**: 4 independent validation gates (step-size, balance, authority, limits)
- **Zero-Sum Constraint**: Strict balancing prevents unauthorized budget growth
- **Complete Audit Trail**: Every adjustment and expenditure logged as immutable event
- **Automatic Triggers**: Balance violations and overspending detected automatically
- **Graduated Constraints**: Large cuts require many small steps (anti-manipulation)

### Resources Module
- **Constitutional Procurement**: Algorithmic supplier selection (rotation, random, hybrid)
- **Feasibility Constraints**: Capacity, certification, experience, and reputation thresholds
- **Anti-Capture Safeguards**: Gini coefficient monitoring, concentration alerts
- **Auditable Selection**: Deterministic seed-based randomness with cryptographic strength
- **Reputation System**: Performance-based scoring with automatic threshold enforcement

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
    scope={"territory": "Albuquerque District 5"},
    reversibility_class="SEMI_REVERSIBLE",
    checkpoints=[30, 90, 180, 365, 1095, 2920, 5475],  # Days until review required
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

# Register suppliers with evidence-based capabilities (v0.3)
supplier = ftl.register_supplier(
    name="SecureInfraCo",
    supplier_type="company",
    metadata={"contact": "ops@secureinfra.com"}
)

# Add capability with evidence (no self-certification)
ftl.add_capability_claim(
    supplier_id=supplier["supplier_id"],
    capability_type="ISO27001",
    evidence=["cert-12345", "audit-report-2024.pdf"],
    capacity_metrics={"concurrent_projects": 5}
)

# Create tender with binary requirements
tender = ftl.create_tender(
    law_id=law["law_id"],
    title="Security Infrastructure Upgrade",
    requirements=[
        {"type": "ISO27001", "min_capacity": 3}
    ],
    budget_allocated=Decimal("500000"),
    selection_method="ROTATION"  # or RANDOM, HYBRID
)

# Open, evaluate, and select supplier constitutionally
ftl.open_tender(tender["tender_id"])
ftl.evaluate_tender(tender["tender_id"])  # Computes feasible set
selected = ftl.select_supplier(tender["tender_id"])  # Deterministic selection

# Award contract and track delivery
ftl.award_tender(tender["tender_id"], contract_terms={"sla_days": 90})
ftl.record_milestone(tender["tender_id"], milestone="Phase 1", evidence=["deploy-logs"])
ftl.complete_tender(tender["tender_id"], quality_score=0.95)  # Updates reputation
```

### Command-Line Interface

```bash
# Initialize database
ftl init --db governance.db

# Create workspace
ftl workspace create --name "Health Services" --scope '{"territory":"Albuquerque"}'

# Delegate decision rights (max 365 days)
ftl delegate create --from alice --to bob --workspace <workspace_id> --ttl-days 180

# Create law with checkpoints
ftl law create \
  --workspace <workspace_id> \
  --title "Primary Care Pilot" \
  --reversibility SEMI_REVERSIBLE \
  --checkpoints 30,90,180,365 \
  --scope '{"territory":"Albuquerque District 5"}'

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

# Supplier management (v0.3)
ftl supplier register --name "SecureInfraCo" --type company
ftl supplier add-capability --supplier-id <id> --capability ISO27001 \
  --evidence '["cert-12345"]' --capacity '{"concurrent_projects":5}'
ftl supplier list
ftl supplier show --id <supplier_id>

# Tender lifecycle (constitutional procurement)
ftl tender create --law-id <id> --title "Security Upgrade" \
  --requirements '[{"type":"ISO27001","min_capacity":3}]' \
  --budget-allocated 500000 --selection-method ROTATION
ftl tender open --id <tender_id> --deadline "2025-12-31T23:59:59"
ftl tender evaluate --id <tender_id>  # Compute feasible set
ftl tender select --id <tender_id>     # Algorithmic selection (no discretion)
ftl tender award --id <tender_id>      # Award contract
ftl tender list --status OPEN
ftl tender show --id <tender_id>

# Delivery tracking
ftl delivery milestone --tender-id <id> --milestone "Phase 1" \
  --evidence '["deploy-logs.txt"]'
ftl delivery complete --tender-id <id> --quality-score 0.95
ftl delivery list --tender <tender_id>
```

## Installation

```bash
# From source
git clone https://github.com/symbolic-labs-pub/freedom-that-lasts
cd freedom-that-lasts
pip install -e ".[dev]"

# Run tests
pytest

# Run examples
python examples/city_pilot.py       # Law & delegation example
python examples/budget_example.py   # Budget module examples (5 scenarios)
python examples/resource_example.py # Resource module examples (5 scenarios)
```

## Current Status:

### v0.1: Governance Kernel
- **Kernel**: Event store (SQLite), projection store, IDs (UUIDv7), time abstraction, SafetyPolicy
- **Law Module**: Workspace management, delegation DAG with TTL/expiry, law lifecycle (DRAFT→ACTIVE→REVIEW→SUNSET)
- **Safeguards**: Delegation concentration metrics (Gini), FreedomHealth scorecard, reflex triggers
- **Tick Engine**: Automatic safeguard evaluation with warnings/halts
- **FTL Façade**: High-level Python API hiding event sourcing complexity
- **CLI**: Complete typer-based CLI (init, workspace, delegate, law, tick, health, safety)
- **Documentation**: ARCHITECTURE.md, THREAT_MODEL.md
- **Examples**: city_pilot.py, replay_demo.py
- **Tests**: 76 tests, 72% coverage

### v0.2: Budget Module
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

### v0.3: Resources Module
- **Tender Aggregate**: Law-scoped procurement with constitutional supplier selection
- **Selection Mechanisms**: Rotation (load-balancing), random (fairness), hybrid (balanced)
- **Feasibility Constraints**: Capacity, certification, experience, reputation thresholds
- **Commands & Events**: CreateTender, SubmitBid, EvaluateBids, SelectSupplier, AwardContract
- **Projections**: TenderRegistry, SupplierRegistry, ContractRegistry
- **Triggers**: Concentration monitoring, feasibility violations, reputation thresholds
- **Anti-Capture**: Gini coefficient calculation, supplier share tracking, rotation enforcement
- **CLI**: 12 tender/supplier/contract commands
- **Documentation**: ARCHITECTURE.md updated with resource module design
- **Examples**: procurement_example.py (constitutional selection scenarios)
- **Tests**: 30+ resource tests (selection algorithms, constraints, projections, triggers)
- **Coverage**: 85%+ across all resource components

### v1.0: Security & Hardening
- **Cryptographic RNG**: `secrets.token_urlsafe()` for correlation IDs, SHA-256 for deterministic selection
- **Path Traversal Protection**: Validated database paths with canonical resolution and base directory enforcement
- **HTTP Security Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, XSS protection
- **Rate Limiting**: Flask-Limiter with graduated limits (10-30 req/min) on health endpoints
- **PII Redaction**: Automatic field-based redaction in logs (actor_id, amount, tokens, secrets)
- **Environment-Aware Logging**: Stack traces suppressed in production (`ENVIRONMENT=production`)
- **Container Hardening**: Read-only filesystems, tmpfs mounts, non-root users (UID 1001), localhost binding
- **Supply Chain Security**: Pinned Docker images to specific versions, GitHub Actions to commit SHAs
- **Dependencies**: CVE scanning (pip-audit), vulnerability database (safety), security analysis (bandit)
- **Tests**: 252 tests passing, 63% coverage
- **Documentation**: THREAT_MODEL.md updated with security controls

## Architecture

```
Event Sourcing Foundation
├── Events (immutable facts)
├── Commands (intentions)
├── Projections (read models)
└── Triggers (automatic reflexes)

Domain Modules
├── Law (delegation, lifecycle, checkpoints)
├── Budget (flex classes, multi-gate enforcement)
├── Resources (constitutional procurement, selection)
├── Feedback (FreedomHealth, triggers)
└── CLI (user interface)

Anti-Tyranny Safeguards
├── Delegation TTL (max 365 days)
├── Concentration metrics (Gini warnings)
├── Checkpoint enforcement (mandatory review)
├── Privacy-by-default (aggregate transparency, PII redaction)
├── Budget flex classes (graduated constraints)
├── Zero-sum balancing (prevent budget growth)
├── Multi-gate validation (defense in depth)
├── Algorithmic selection (no discretion, no favoritism)
├── Supplier rotation (anti-monopolization)
├── Cryptographic randomness (auditable fairness)
└── Security hardening (container isolation, rate limiting, path validation)
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
- [THREAT_MODEL.md](../THREAT_MODEL.md) - Anti-tyranny safeguards and threat analysis
- [Examples](examples/) - Working code examples:
  - `city_pilot.py` - Law lifecycle and delegation example
  - `replay_demo.py` - Event sourcing demonstration
  - `budget_example.py` - Budget module comprehensive examples (5 scenarios)
  - `resource_example.py` - Resource module procurement examples (5 scenarios: tender lifecycle, multi-gate selection, feasible set, concentration monitoring, delivery tracking)

## Contributing

This is an open development - contributions welcome! See implementation plan for detailed tasks.

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

**Fun Fact**: The average lifespan of a democracy is around 200 years. This framework aims to extend that by making freedom structurally stable, not just aspirational.
