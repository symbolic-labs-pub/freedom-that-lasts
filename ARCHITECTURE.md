# Architecture

Freedom That Lasts is an event-sourced governance system designed with structural resistance to tyranny, power entrenchment, and irreversible drift.

## Design Philosophy

**Core Principle**: Preserve future option space through architectural constraints that make tyranny expensive and reversibility cheap.

The system embeds anti-tyranny safeguards directly into the architecture rather than relying on policy enforcement or human vigilance:

- **Event Sourcing**: Immutable audit trail of all governance decisions
- **Time-Bounded Authority**: All delegations expire (max 365 days)
- **Mandatory Reviews**: Laws require checkpoint reviews at defined intervals
- **Automatic Triggers**: System reflexes detect and halt concentration of power
- **Privacy by Default**: Delegation visibility protects against coercion
- **Structural Acyclicity**: Delegation graph cannot form cycles (prevents circular authority)

## Event Sourcing Architecture

### Core Concepts

**Event Store**: Append-only log of immutable events, source of truth for all state

**Projections**: Materialized read models rebuilt from events

**Commands**: Write operations that generate events

**Invariants**: Pure validation functions enforcing business rules

**Triggers**: Automatic reflex events emitted on threshold violations

### Data Flow

```
┌─────────────┐
│   Command   │  (CreateLaw, DelegateDecisionRight, etc.)
└──────┬──────┘
       │
       v
┌─────────────────┐
│  Invariants     │  (Validate TTL, check cycles, etc.)
│  Validation     │
└──────┬──────────┘
       │
       v
┌─────────────────┐
│  Command        │  (Business logic)
│  Handler        │
└──────┬──────────┘
       │
       v
┌─────────────────┐
│  Events         │  (LawCreated, DecisionRightDelegated, etc.)
└──────┬──────────┘
       │
       v
┌─────────────────┐
│  Event Store    │  (Append-only SQLite)
│  (SQLite)       │
└──────┬──────────┘
       │
       v
┌─────────────────┐
│  Projections    │  (LawRegistry, DelegationGraph, etc.)
│  (Update)       │
└─────────────────┘
```

### Tick Loop (Safeguard Evaluation)

```
┌─────────────┐
│  ftl.tick() │
└──────┬──────┘
       │
       v
┌─────────────────────────────┐
│  Load All Projections       │
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│  Evaluate Triggers          │
│  - Delegation concentration │
│  - Law checkpoint deadlines │
│  - TTL expirations          │
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│  Emit Reflex Events         │
│  - Warnings                 │
│  - Halts                    │
│  - Review triggers          │
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│  Store Events & Update      │
│  Projections                │
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│  Return TickResult          │
│  (FreedomHealth + Events)   │
└─────────────────────────────┘
```

## Database Schema

### Events Table (Append-Only)

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,          -- UUIDv7 (time-sortable)
    stream_id TEXT NOT NULL,            -- Aggregate root ID
    stream_type TEXT NOT NULL,          -- "workspace", "law", "delegation"
    version INTEGER NOT NULL,           -- Stream version (optimistic locking)
    command_id TEXT NOT NULL UNIQUE,    -- Idempotency key
    event_type TEXT NOT NULL,           -- "LawActivated", "DecisionRightDelegated", etc.
    occurred_at TEXT NOT NULL,          -- ISO 8601 timestamp
    actor_id TEXT,                      -- Who triggered this event
    payload_json TEXT NOT NULL,         -- Event payload (JSON)

    UNIQUE(stream_id, version)          -- Ensures version sequence
);

CREATE INDEX idx_events_stream ON events(stream_id, version);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_occurred_at ON events(occurred_at);
```

**Key Properties**:
- **Append-only**: Events never updated or deleted
- **Versioned**: Stream version prevents concurrent modification conflicts
- **Idempotent**: Same command_id cannot create duplicate events
- **Time-ordered**: UUIDv7 provides temporal ordering

### Projections Table

```sql
CREATE TABLE projections (
    name TEXT PRIMARY KEY,              -- Projection name
    position_event_id TEXT NOT NULL,    -- Last processed event
    state_json TEXT NOT NULL,           -- Projection state (JSON)
    updated_at TEXT NOT NULL            -- Last update timestamp
);
```

Projections are materialized views rebuilt from events. If corrupted, can be dropped and rebuilt deterministically.

## Domain Model

### Core Aggregates

#### Workspace
Hierarchical scopes for governance (e.g., "Health Services District 5")

```python
class Workspace:
    workspace_id: str
    name: str
    parent_workspace_id: str | None
    scope: dict                         # Territory, domain, etc.
    created_at: datetime
    archived_at: datetime | None
```

#### Delegation
Time-bounded transfer of decision rights

```python
class Delegation:
    delegation_id: str
    workspace_id: str                   # Scope of delegation
    from_actor: str
    to_actor: str
    ttl_days: int                       # <= max_delegation_ttl_days (365)
    expires_at: datetime                # Auto-computed
    visibility: str                     # "private" | "org_only" | "public"
    revoked_at: datetime | None
    created_at: datetime
```

**Anti-Tyranny Properties**:
- **Max TTL**: Cannot exceed 365 days (safety policy)
- **Expiry**: Must be explicitly renewed (no automatic renewal)
- **Acyclic**: Graph validation prevents delegation cycles
- **Revocable**: Can be revoked by delegator at any time

#### Law
Time-bounded rule with mandatory review checkpoints

```python
class Law:
    law_id: str
    workspace_id: str                   # Parent workspace
    title: str
    scope: dict                         # Territory, validity, etc.
    reversibility_class: ReversibilityClass  # REVERSIBLE | SEMI_REVERSIBLE | IRREVERSIBLE
    checkpoints: list[int]              # Review schedule (days): [30, 90, 180, 365]
    params: dict                        # Law-specific parameters
    status: LawStatus                   # DRAFT | ACTIVE | REVIEW | SUNSET | ARCHIVED
    next_checkpoint_at: datetime | None
    created_at: datetime
    activated_at: datetime | None
    version: int                        # Optimistic locking
```

**Lifecycle**:
```
DRAFT → ACTIVE → REVIEW → ACTIVE (continue)
                      ↓
                   SUNSET → ARCHIVED
```

**Anti-Tyranny Properties**:
- **Mandatory Reviews**: Must be reviewed at checkpoints or auto-triggered for review
- **Reversibility Classes**: Irreversible laws face stricter requirements
- **Time-Bounded**: No permanent laws without review

### Projections

#### LawRegistry
Materialized view of all laws with status filtering

```python
class LawRegistry:
    laws: dict[str, dict]               # law_id → law state

    def list_active(self) -> list[dict]
    def list_overdue_reviews(self, now: datetime) -> list[dict]
    def list_by_status(self, status: LawStatus) -> list[dict]
```

#### DelegationGraph
Directed acyclic graph of active delegations

```python
class DelegationGraph:
    delegations: dict[str, dict]        # delegation_id → delegation state
    edges: list[tuple[str, str]]        # (from_actor, to_actor) pairs

    def get_active_edges(self, now: datetime) -> list[tuple[str, str]]
    def get_in_degree(self, actor: str, now: datetime) -> int
    def would_create_cycle(self, from_actor: str, to_actor: str) -> bool
```

**Invariant**: Graph must remain acyclic at all times

#### FreedomHealthProjection
Anti-tyranny scorecard with concentration metrics

```python
class FreedomHealthScore:
    risk_level: RiskLevel               # GREEN | YELLOW | RED
    concentration: ConcentrationMetrics
    law_review_health: LawReviewHealth
    reasons: list[str]                  # Why this risk level?
    computed_at: datetime
```

## Safeguards

### 1. Delegation Concentration Detection

**Metrics**:
- **Gini Coefficient**: Measures inequality in delegation distribution (0 = perfect equality, 1 = total concentration)
- **Max In-Degree**: Maximum number of delegations received by any single actor

**Thresholds** (SafetyPolicy):
```python
delegation_gini_warn: 0.55              # Yellow zone
delegation_gini_halt: 0.70              # Red zone - halt new delegations
delegation_in_degree_warn: 500
delegation_in_degree_halt: 2000
```

**Trigger Logic**:
```python
if gini >= policy.delegation_gini_halt:
    emit DelegationConcentrationHalt()
    emit TransparencyEscalated(scope=workspace_id, level="aggregate_plus")
elif gini >= policy.delegation_gini_warn:
    emit DelegationConcentrationWarning()
```

### 2. Law Checkpoint Enforcement

**Mechanism**: Every active law has `next_checkpoint_at`. Tick loop checks for overdue checkpoints.

**Trigger Logic**:
```python
for law in active_laws:
    if now > law.next_checkpoint_at:
        emit LawReviewTriggered(
            law_id=law.law_id,
            reason="checkpoint_overdue"
        )
```

**Status Transition**: `ACTIVE` → `REVIEW` (blocks further changes until review completed)

### 3. TTL Enforcement

**Creation-Time Check**:
```python
if ttl_days > policy.max_delegation_ttl_days:
    raise TTLExceedsMaximum(f"TTL {ttl_days} exceeds max {policy.max_delegation_ttl_days}")
```

**Expiry Check** (in tick loop):
```python
if now > delegation.expires_at and not delegation.revoked_at:
    emit DelegationExpired(delegation_id=delegation.delegation_id)
```

### 4. Acyclic Graph Enforcement

**Algorithm**: Depth-first search from `to_actor` to detect path to `from_actor`

```python
def would_create_cycle(graph: DelegationGraph, from_actor: str, to_actor: str) -> bool:
    """Check if adding edge (from_actor → to_actor) creates cycle"""
    visited = set()

    def dfs(node: str) -> bool:
        if node == from_actor:
            return True  # Cycle detected
        if node in visited:
            return False
        visited.add(node)
        for (source, target) in graph.edges:
            if source == node:
                if dfs(target):
                    return True
        return False

    return dfs(to_actor)
```

**Enforcement**:
```python
if would_create_cycle(delegation_graph, from_actor, to_actor):
    raise DelegationCycleDetected(f"Delegation {from_actor} → {to_actor} would create cycle")
```

## Idempotency

### Command Idempotency

Every command has a `command_id` (UUIDv7). Event store enforces uniqueness:

```python
def append(self, stream_id: str, expected_version: int, events: list[Event]) -> None:
    for event in events:
        # Check if command already processed
        existing = cursor.execute(
            "SELECT event_id FROM events WHERE command_id = ?",
            (event.command_id,)
        ).fetchone()

        if existing:
            return  # Already processed, skip silently

        # Insert event...
```

**Result**: Running same command multiple times produces same outcome (exactly-once semantics)

### Event Replay Determinism

Projections are rebuilt by replaying events in order:

```python
def _rebuild_projections(self):
    all_events = self.event_store.load_all_events()
    for event in all_events:
        # Apply to appropriate projections
        if event.event_type.startswith("Law"):
            self.law_registry.apply_event(event)
        elif event.event_type in ["DecisionRightDelegated", ...]:
            self.delegation_graph.apply_event(event)
        # ...
```

**Guarantee**: Same events in same order → identical projection state

## Versioning and Concurrency

### Optimistic Locking

Each stream (law, delegation, workspace) has a version counter:

```sql
UNIQUE(stream_id, version)
```

**Write Flow**:
1. Read current version: `law.version = 3`
2. Create event: `event.version = 4`
3. Append with expected version: `event_store.append(stream_id, expected_version=3, [event])`
4. Database enforces: `expected_version` must match current max version
5. If mismatch → `StreamVersionConflict` exception

**Result**: Concurrent writes are detected and rejected

### Version Management

**In FTL Façade**:
```python
def activate_law(self, law_id: str, actor_id: str = "system") -> dict[str, Any]:
    law = self.law_registry.get(law_id)
    current_version = law["version"] if law else 0

    events = self.handlers.handle_activate_law(command, generate_id(), actor_id, laws)

    for event in events:
        self.event_store.append(event.stream_id, current_version, [event])
        self.law_registry.apply_event(event)
        current_version = event.version  # Update for next event

    return self.law_registry.get(law_id)
```

## Testing Strategy

### Unit Tests
- **Invariants**: 100% coverage on validation logic
- **Handlers**: Test command → event transformations
- **Projections**: Test event application and queries
- **Triggers**: 100% coverage on threshold detection

### Integration Tests
- **Complete Workflows**: Create workspace → Delegate → Create law → Activate → Tick → Review
- **Trigger Cascades**: Concentration breach → Warning → Halt → Escalation
- **Idempotency**: Run same command twice, verify single event
- **Replay**: Store events, rebuild projections, verify state

### Test Coverage Requirements
- **Minimum**: 90% line coverage
- **Critical Paths**: 100% coverage on invariants and triggers
- **Branch Coverage**: Enabled for all modules

## Performance Characteristics

### Event Store
- **Append Rate**: >1000 events/sec (SQLite WAL mode)
- **Query Performance**: <10ms for single stream load
- **Storage**: ~1KB per event average

### Projections
- **Rebuild Time**: <10sec for 10,000 events
- **Query Performance**: <100ms for complex queries (in-degree computation)
- **Memory**: All projections fit in memory for <100K entities

### Tick Loop
- **Evaluation Time**: <500ms for 1000 active laws + 10,000 delegations
- **Trigger Latency**: <1sec from threshold violation to event emission

## Security Properties

### Audit Trail
- **Immutable**: Events cannot be deleted or modified
- **Complete**: Every state change captured
- **Timestamped**: Temporal ordering preserved
- **Actor-Attributed**: Every event records who triggered it

### Privacy
- **Delegation Visibility**: Default "private" (only participants see)
- **Aggregate Metrics**: Concentration metrics exposed without individual data
- **Coercion Resistance**: No proof-of-vote artifacts

### Transparency Escalation
When halt conditions detected:
```python
emit TransparencyEscalated(
    scope=workspace_id,
    level="aggregate_plus"  # More detailed metrics published
)
```

**Purpose**: Make power concentration visible while preserving privacy in normal operation

## Extension Points

### Custom Triggers
Add new trigger functions:

```python
def evaluate_custom_trigger(
    projections: dict,
    policy: SafetyPolicy,
    now: datetime
) -> list[Event]:
    # Custom logic
    if condition:
        return [CustomWarning(...)]
    return []

# Register in TickEngine
tick_engine.register_trigger(evaluate_custom_trigger)
```

### Custom Projections
Implement `apply_event()` method:

```python
class CustomProjection:
    def apply_event(self, event: Event) -> None:
        if event.event_type == "CustomEvent":
            # Update state
            pass
```

### Custom Commands
Add new command handlers:

```python
def handle_custom_command(
    command: CustomCommand,
    command_id: str,
    actor_id: str,
    projections: dict
) -> list[Event]:
    # Validate
    # Generate events
    return [CustomEvent(...)]
```

## Future Architecture

### v0.2: Budget Module
- Budget stream with events: BudgetAllocated, ExpenditureApproved
- StepSize engine (multi-gate enforcement)
- Balancing engine (prevent drift)

### v0.3: Resource Module
- Capability registry
- Feasible set computation
- Supplier selection (rotation + auditable random)

### v1.0: Distributed Event Store
- Multi-node event store with consensus
- Distributed projections
- Global safeguards across nodes

## References

- **Event Sourcing**: Martin Fowler - https://martinfowler.com/eaaDev/EventSourcing.html
- **CQRS**: Greg Young - https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
- **UUIDv7**: RFC 9562 - https://www.rfc-editor.org/rfc/rfc9562.html
