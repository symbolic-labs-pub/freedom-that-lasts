# Threat Model

This document analyzes threats to freedom in governance systems and how Freedom That Lasts mitigates them through structural safeguards.

## Core Threat: Erosion of Future Option Space

**Definition**: Freedom = ability for future generations to make different choices

**Primary Threat Vector**: Irreversible decisions that lock in current preferences and eliminate future alternatives

### Threat Taxonomy

```
Threats to Freedom
├── Power Entrenchment
│   ├── Delegation concentration (oligarchy formation)
│   ├── Permanent authority grants (no sunset)
│   └── Circular delegation (authority loops)
│
├── Irreversible Drift
│   ├── Laws without review mechanisms
│   ├── Permanent resource commitments
│   └── Constitutional amendments without safeguards
│
├── Coercion & Privacy Violations
│   ├── Vote-buying (proof of vote required)
│   ├── Intimidation (forced disclosure)
│   └── Social pressure (public voting)
│
└── Coordination Failures
    ├── Complexity overwhelm (too many choices)
    ├── Information asymmetry (hidden concentrations)
    └── Threshold effects (cliff-edge collapses)
```

## Threat 1: Delegation Concentration (Oligarchy Formation)

### Attack Scenario

**Attacker Goal**: Accumulate decision authority from many actors to create de facto control

**Attack Sequence**:
1. Legitimate actor offers to "help coordinate" decision-making
2. Many actors delegate to this coordinator (appears efficient)
3. Coordinator accumulates delegations from thousands of actors
4. Coordinator now controls supermajority of decision rights
5. System has become oligarchy despite democratic structure

**Without Safeguards**: This is the natural attractor state (coordination is genuinely useful, delegation happens gradually and appears rational at each step)

### FTL Mitigation: Concentration Metrics + Automatic Halts

#### Detection: Gini Coefficient

**Metric**: Gini coefficient of delegation in-degree distribution
- 0.0 = perfect equality (all actors receive same number of delegations)
- 1.0 = total concentration (one actor receives all delegations)

**Calculation**:
```python
def compute_gini_coefficient(in_degrees: list[int]) -> float:
    """Compute Gini coefficient of delegation concentration"""
    if not in_degrees:
        return 0.0

    sorted_degrees = sorted(in_degrees)
    n = len(sorted_degrees)
    cumsum = 0.0
    for i, degree in enumerate(sorted_degrees):
        cumsum += (i + 1) * degree

    total = sum(sorted_degrees)
    if total == 0:
        return 0.0

    return (2 * cumsum) / (n * total) - (n + 1) / n
```

**Thresholds** (SafetyPolicy):
```python
delegation_gini_warn: 0.55      # Yellow zone - warning issued
delegation_gini_halt: 0.70      # Red zone - new delegations halted
```

#### Enforcement: Automatic Triggers

**Warning Phase** (Gini >= 0.55):
```python
if gini >= policy.delegation_gini_warn and gini < policy.delegation_gini_halt:
    emit DelegationConcentrationWarning(
        gini_coefficient=gini,
        max_in_degree=max(in_degrees),
        threshold=policy.delegation_gini_warn
    )
```

**Outcome**: System alerts operators, no action blocked

**Halt Phase** (Gini >= 0.70):
```python
if gini >= policy.delegation_gini_halt:
    emit DelegationConcentrationHalt(
        gini_coefficient=gini,
        max_in_degree=max(in_degrees),
        threshold=policy.delegation_gini_halt
    )
    emit TransparencyEscalated(
        scope=workspace_id,
        level="aggregate_plus",
        reason="concentration_halt"
    )
```

**Outcome**:
1. New delegations to high in-degree actors **rejected**
2. Transparency escalated (more detailed metrics published)
3. System enters elevated monitoring mode

#### Cost Imposed on Attacker

**Economic**: Accumulating delegations becomes exponentially harder as concentration increases
**Temporal**: Delegations have max TTL of 365 days - must be continuously renewed
**Detection**: Automatic transparency escalation makes concentration visible
**Reputational**: Halt events are permanently logged in immutable audit trail

### Layered Defense

**Layer 1**: Max In-Degree Threshold
```python
delegation_in_degree_warn: 500
delegation_in_degree_halt: 2000
```

**Layer 2**: Max TTL Enforcement
```python
max_delegation_ttl_days: 365
delegation_requires_renewal: True
```

**Layer 3**: Acyclic Graph Constraint
```python
if would_create_cycle(delegation_graph, from_actor, to_actor):
    raise DelegationCycleDetected(...)
```

**Result**: Multiple independent safeguards must all be bypassed for attack to succeed

## Threat 2: Irreversible Drift

### Attack Scenario

**Attacker Goal**: Enact permanent laws that future generations cannot change

**Attack Sequence**:
1. Pass law with no review mechanism
2. Law continues indefinitely without oversight
3. Context changes but law remains
4. Future actors inherit irreversible constraints
5. Option space permanently reduced

**Real-World Example**: Permanent debt obligations, constitutional amendments without sunset clauses, perpetual resource commitments

### FTL Mitigation: Mandatory Review Checkpoints

#### Enforcement: Checkpoint Schedule

Every law must define review checkpoints:
```python
checkpoints: list[int] = [30, 90, 180, 365]  # Days from activation
```

**At Activation**:
```python
law.next_checkpoint_at = law.activated_at + timedelta(days=checkpoints[0])
law.checkpoint_index = 0
```

**Tick Loop Detection**:
```python
def evaluate_law_checkpoints(laws: list[Law], now: datetime) -> list[Event]:
    events = []
    for law in laws:
        if law.status == LawStatus.ACTIVE and now > law.next_checkpoint_at:
            events.append(LawReviewTriggered(
                law_id=law.law_id,
                checkpoint_index=law.checkpoint_index,
                scheduled_at=law.next_checkpoint_at,
                triggered_at=now,
                reason="checkpoint_overdue"
            ))
    return events
```

**Status Transition**: `ACTIVE` → `REVIEW` (automatic)

**Enforcement**: Law **cannot be modified or relied upon** while in `REVIEW` status until review completed

#### Review Outcomes

**Continue**: Law returns to `ACTIVE`, next checkpoint scheduled
```python
law.status = LawStatus.ACTIVE
law.checkpoint_index += 1
if law.checkpoint_index < len(law.checkpoints):
    law.next_checkpoint_at = now + timedelta(days=law.checkpoints[law.checkpoint_index])
```

**Adjust**: Law parameters modified, returns to `ACTIVE`, checkpoints reset
**Sunset**: Law transitions to `SUNSET` → `ARCHIVED`, no longer active

#### Reversibility Classes

Laws categorized by reversibility to adjust safeguards:

```python
class ReversibilityClass(str, Enum):
    REVERSIBLE = "REVERSIBLE"              # Easy to undo (policy changes)
    SEMI_REVERSIBLE = "SEMI_REVERSIBLE"    # Costly but possible (infrastructure)
    IRREVERSIBLE = "IRREVERSIBLE"          # Cannot undo (genetic editing)
```

**Future Enhancement**: Stricter checkpoints for `IRREVERSIBLE` class (e.g., 7, 14, 30, 60 days)

### Cost Imposed on Attacker

**Temporal**: Cannot create permanent laws without ongoing review
**Transparency**: Review process is public, creates accountability
**Coordination**: Must repeatedly convince reviewers law should continue
**Audit Trail**: All review decisions permanently logged

## Threat 3: Coercion Through Vote Visibility

### Attack Scenario

**Attacker Goal**: Force actors to vote specific way through intimidation or vote-buying

**Attack Sequence**:
1. Attacker demands proof of vote from actor
2. Actor must prove they delegated/voted as instructed
3. Attacker can verify compliance (or lack thereof)
4. Attacker punishes non-compliance
5. Delegation becomes coerced, not voluntary

**Real-World Examples**: Vote buying in public blockchain voting, employer intimidation in open-ballot systems, social pressure in transparent voting

### FTL Mitigation: Privacy by Default

#### Delegation Visibility Levels

```python
class DelegationVisibility(str, Enum):
    PRIVATE = "private"          # Only delegator and delegate see it
    ORG_ONLY = "org_only"        # Organization members see it
    PUBLIC = "public"            # Anyone sees it
```

**Default**: `PRIVATE`

**Enforcement**:
```python
class Delegation:
    visibility: str = "private"  # Default in model
```

#### Aggregate Transparency

**Public Metrics** (no individual data):
```python
class ConcentrationMetrics:
    gini_coefficient: float              # Overall concentration
    max_in_degree: int                   # Highest delegation count (no actor ID)
    total_active_delegations: int
    unique_delegates: int
    in_degree_distribution: dict[str, int]  # Bucketed: {"0-10": 45, "11-50": 12, ...}
```

**Private Data** (not exposed):
- Individual delegation edges (who delegated to whom)
- Actor-specific delegation counts
- Delegation timestamps (could reveal patterns)

#### Transparency Escalation

**Trigger**: When concentration reaches halt threshold
```python
if gini >= policy.delegation_gini_halt:
    emit TransparencyEscalated(
        scope=workspace_id,
        level="aggregate_plus",
        reason="concentration_halt"
    )
```

**Escalated Metrics** (still aggregate):
- Top 10 in-degree counts (no actor IDs)
- Concentration by workspace
- Time-series of concentration metrics

**Never Disclosed**: Individual delegation edges

### No Proof-of-Vote Artifacts

**Forbidden Features** (intentionally not implemented):
- Delegation receipts
- Cryptographic vote proofs
- Public delegation ledger with actor IDs
- NFTs or tokens representing delegations

**Rationale**: If proof is possible, coercion becomes profitable

### Cost Imposed on Attacker

**Technical**: Cannot verify individual votes/delegations
**Economic**: Vote-buying becomes unenforceable
**Social**: Intimidation requires surveillance outside system (expensive)

## Threat 4: Circular Authority (Bootstrap Problem)

### Attack Scenario

**Attacker Goal**: Create circular delegation allowing self-delegation or authority loops

**Attack Sequence**:
1. Alice delegates to Bob
2. Bob delegates to Carol
3. Carol delegates back to Alice
4. Alice now has her own authority plus Bob's and Carol's
5. Authority amplified through cycle

**Graph Theory**: Cycle in directed graph creates feedback loop

### FTL Mitigation: Acyclic Delegation DAG

#### Constraint: Directed Acyclic Graph (DAG)

**Invariant**: Delegation graph must never contain cycles

**Validation** (before creating delegation):
```python
def would_create_cycle(graph: DelegationGraph, from_actor: str, to_actor: str) -> bool:
    """DFS to check if adding edge creates cycle"""
    visited = set()

    def dfs(node: str) -> bool:
        if node == from_actor:
            return True  # Found cycle
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
# In handle_delegate_decision_right
if would_create_cycle(delegation_graph, command.from_actor, command.to_actor):
    raise DelegationCycleDetected(
        f"Delegation {command.from_actor} → {command.to_actor} would create cycle"
    )
```

**Result**: Delegation creation **fails** if cycle detected

#### Properties of DAG

**Topological Ordering**: Clear hierarchy of authority
**Finite Traversal**: Can compute transitive closure
**No Infinite Loops**: Authority chains always terminate

### Cost Imposed on Attacker

**Structural**: Mathematically impossible to create cycle
**Detection**: Cycle check runs on every delegation
**Performance**: O(V+E) DFS, cheap for reasonable graph sizes

## Threat 5: Permanent Delegation (Authority Entrenchment)

### Attack Scenario

**Attacker Goal**: Obtain delegation with no expiry, creating permanent authority

**Attack Sequence**:
1. Attacker receives delegation
2. Delegation has no time limit
3. Delegator loses interest or dies
4. Delegation continues indefinitely
5. Authority entrenched without ongoing consent

**Real-World Example**: Appointed positions without term limits, perpetual proxies in corporate governance

### FTL Mitigation: Mandatory TTL with Maximum

#### Constraint: Time-to-Live Required

**Every delegation must have TTL**:
```python
class Delegation:
    ttl_days: int                       # Required field
    expires_at: datetime                # Auto-computed from ttl_days
```

**Computation**:
```python
delegation.expires_at = delegation.created_at + timedelta(days=delegation.ttl_days)
```

#### Maximum TTL Enforcement

**Safety Policy**:
```python
max_delegation_ttl_days: 365            # One year maximum
```

**Validation**:
```python
if command.ttl_days > safety_policy.max_delegation_ttl_days:
    raise TTLExceedsMaximum(
        f"TTL {command.ttl_days} exceeds maximum {safety_policy.max_delegation_ttl_days}"
    )
```

**Result**: Cannot create delegation >365 days

#### Expiry Detection

**Tick Loop**:
```python
def evaluate_delegation_expiry(delegations: list[Delegation], now: datetime) -> list[Event]:
    events = []
    for delegation in delegations:
        if not delegation.revoked_at and now > delegation.expires_at:
            events.append(DelegationExpired(
                delegation_id=delegation.delegation_id,
                from_actor=delegation.from_actor,
                to_actor=delegation.to_actor,
                expired_at=now
            ))
    return events
```

**Outcome**: Expired delegations automatically invalidated

#### Renewal Requirement

**Policy**:
```python
delegation_requires_renewal: True       # No automatic renewal
```

**Enforcement**: Delegator must **explicitly** create new delegation after expiry

**Rationale**: Forces ongoing consent, prevents forgotten delegations

### Cost Imposed on Attacker

**Temporal**: Must renew delegation every year
**Coordination**: Must maintain relationship with delegator
**Detection**: Expiry events logged in audit trail
**Reputational**: High churn rate signals instability

## Threat 6: Complexity Overwhelm

### Attack Scenario

**Attacker Goal**: Create so many delegations/laws that oversight becomes impossible

**Attack Sequence**:
1. System allows unlimited laws/delegations
2. Attacker creates thousands of laws
3. Each law requires review at checkpoints
4. Review capacity overwhelmed
5. Laws rubber-stamped without real oversight
6. System collapses under cognitive load

**Real-World Example**: Tax code complexity, regulatory proliferation

### FTL Mitigation: Bounded Cognitive Load

#### Future Safeguards (v0.2+)

**Law Count Limits** (per workspace):
```python
max_active_laws_per_workspace: int = 100
```

**Review Batching**:
```python
# Group laws by checkpoint proximity
# Present related laws together for coherent review
```

**Health Degradation**:
```python
if overdue_reviews > 10:
    health.risk_level = RiskLevel.YELLOW
if overdue_reviews > 50:
    health.risk_level = RiskLevel.RED
    emit ReviewCapacityExceeded(...)
```

#### Current Safeguards

**Visibility**:
```python
health.law_review_health.overdue_reviews       # Exposed in health check
health.law_review_health.upcoming_reviews_7d
health.law_review_health.upcoming_reviews_30d
```

**Early Warning**:
```python
if upcoming_reviews_7d > 5:
    reasons.append(f"High upcoming review load: {upcoming_reviews_7d} in next 7 days")
```

## Threat 7: Database Tampering

### Attack Scenario

**Attacker Goal**: Modify event store to rewrite history (1984-style)

**Attack Sequence**:
1. Attacker gains file system access to SQLite database
2. Attacker modifies events directly via SQL
3. Events appear to show different history
4. Projections rebuilt from tampered events
5. Illegitimate state appears legitimate

### Current Mitigation: Append-Only Events

#### Database Constraints

**Uniqueness**:
```sql
UNIQUE(stream_id, version)              -- Prevents version conflicts
UNIQUE(command_id)                       -- Prevents duplicate commands
PRIMARY KEY(event_id)                    -- Unique event IDs
```

**Immutability** (by convention):
- Events never updated via application code
- No DELETE operations in codebase
- Only INSERT operations for events

#### Detection: Event Hash Chain (Future)

**v0.2 Enhancement**:
```python
class Event:
    event_id: str
    previous_event_hash: str            # Hash of prior event
    event_hash: str                     # Hash of this event
```

**Verification**:
```python
def verify_event_chain(events: list[Event]) -> bool:
    for i, event in enumerate(events[1:], 1):
        expected_hash = compute_hash(events[i-1])
        if event.previous_event_hash != expected_hash:
            raise EventChainBroken(...)
    return True
```

**Result**: Tampering detected if hash chain broken

#### Detection: External Audit Log (Future)

**v0.3 Enhancement**: Write event hashes to external append-only log
- Blockchain (public verifiability)
- Certificate Transparency style log
- Centralized trusted timestamping service

### Current Limitations

**Not Protected Against**:
- Root file system access (can modify SQLite directly)
- Backup restoration to earlier state
- Full database deletion

**Mitigation Strategy**: Operate in trusted environment with proper access controls, regular backups, external audit logs

## Threat 8: Sybil Attacks (Fake Actor Creation)

### Attack Scenario

**Attacker Goal**: Create fake actors to simulate widespread support

**Attack Sequence**:
1. System has no identity verification
2. Attacker creates 1000 fake actor IDs
3. Attacker delegates from fake actors to real actor
4. Real actor appears to have widespread support
5. Concentration metrics show false distribution

**Real-World Example**: Social media bots, fake reviews, astroturfing

### Current Status: Out of Scope for v0.1

**Rationale**: Identity and authentication are distinct concerns

**Assumption**: FTL operates within trusted identity context
- Corporate setting: Employee directory
- Government: Citizen registry
- Open source: GitHub accounts

**Future Enhancement (v0.3)**:
```python
class Actor:
    actor_id: str
    verified_identity: str              # DID, verified credential
    identity_proof: str                 # VC, signature
    reputation_score: float
```

### Partial Mitigation: Gini Still Detects

**Even with Sybils**: If real concentration occurs (via Sybils), Gini increases
- Sybil creator delegates from many fake IDs to one real ID
- In-degree of real ID increases
- Gini coefficient rises
- Halt triggered

**Limitation**: If Sybils evenly distributed, Gini shows false equality

## Threat 9: Time Manipulation

### Attack Scenario

**Attacker Goal**: Manipulate system time to bypass TTL/checkpoint enforcement

**Attack Sequence**:
1. System uses system clock for time
2. Attacker controls system clock
3. Attacker sets clock backward
4. Delegations appear not expired
5. Checkpoints appear not overdue
6. Safeguards bypassed

### FTL Mitigation: Time Provider Abstraction

#### TimeProvider Interface

```python
class TimeProvider(Protocol):
    def now(self) -> datetime:
        """Return current UTC time"""
        ...
```

**Production**:
```python
class RealTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
```

**Testing**:
```python
class TestTimeProvider:
    def __init__(self, initial_time: datetime):
        self._current_time = initial_time

    def now(self) -> datetime:
        return self._current_time

    def advance_days(self, days: int) -> None:
        self._current_time += timedelta(days=days)
```

#### Future Enhancement: External Time Authority

**v0.3**:
```python
class TrustedTimeProvider:
    def now(self) -> datetime:
        # Query multiple NTP servers
        # Verify consensus
        # Detect clock skew
        return verified_time
```

**Use Cases**: Distributed deployments, adversarial environments

### Current Limitations

**Vulnerable to**: System administrator setting clock backward (requires root access)

**Mitigation**: Operate with trusted system administrators, external monitoring

## Threat Matrix

| Threat | Severity | FTL Mitigation | Status | Residual Risk |
|--------|----------|----------------|--------|---------------|
| Delegation Concentration | HIGH | Gini + In-Degree + TTL | ✓ Implemented | LOW - Attack detectable & costly |
| Irreversible Drift | HIGH | Mandatory Checkpoints | ✓ Implemented | LOW - No permanent laws possible |
| Vote Coercion | MEDIUM | Privacy by Default | ✓ Implemented | LOW - No proof-of-vote possible |
| Circular Authority | MEDIUM | Acyclic DAG Constraint | ✓ Implemented | NONE - Mathematically prevented |
| Permanent Delegation | MEDIUM | Max TTL + Expiry | ✓ Implemented | LOW - Max 1 year, renewal required |
| Complexity Overwhelm | MEDIUM | Health Metrics | ⚠ Partial (v0.2) | MEDIUM - Visibility only |
| Database Tampering | LOW | Append-Only + Constraints | ⚠ Partial (v0.2) | MEDIUM - Requires external audit log |
| Sybil Attacks | MEDIUM | Gini (partial) | ❌ Future (v0.3) | HIGH - Identity out of scope |
| Time Manipulation | LOW | TimeProvider Abstraction | ✓ Implemented | LOW - Requires root access |

## Defense in Depth

### Layer 1: Structural Constraints (Preventive)
- Acyclic graph (prevents cycles)
- Max TTL (prevents permanent authority)
- Required checkpoints (prevents permanent laws)

### Layer 2: Automatic Detection (Detective)
- Gini coefficient (detects concentration)
- Tick loop (detects expiry, overdue reviews)
- FreedomHealth scorecard (surfaces risk)

### Layer 3: Automatic Response (Reactive)
- Halt new delegations (concentration threshold)
- Trigger law reviews (overdue checkpoints)
- Transparency escalation (publish more metrics)

### Layer 4: Audit Trail (Forensic)
- Immutable event log
- Actor attribution
- Timestamp ordering
- Replay capability

### Layer 5: Privacy Protection (Coercion Resistance)
- Private delegations by default
- Aggregate metrics only
- No proof-of-vote artifacts

## Attack Cost Analysis

**Cheapest Attack**: Gradual delegation accumulation
- **Cost**: Building trust relationships over time
- **Detection Time**: Continuous (Gini updated every tick)
- **Response Time**: Automatic (halt triggered immediately)
- **Success Probability**: Low (multiple safeguards)

**Most Expensive Attack**: Database tampering + Sybils + time manipulation
- **Cost**: Root access + fake identities + external time authority bypass
- **Detection Time**: Immediate (hash chain broken, Gini spike)
- **Response Time**: System halt + manual investigation
- **Success Probability**: Very low (requires multiple sophisticated capabilities)

**Conclusion**: Tyranny is expensive and detectable. Freedom is the attractor state.

## Future Enhancements

### v0.2: Enhanced Tamper Resistance
- Event hash chains
- External audit log (blockchain or CT-style)
- Multi-signature event signing

### v0.3: Identity Integration
- Decentralized Identifiers (DIDs)
- Verifiable Credentials (VCs)
- Reputation scoring
- Sybil resistance

### v1.0: Distributed Deployment
- Multi-node event store with consensus
- Byzantine fault tolerance
- Global safeguards across instances

## References

- Gini Coefficient: https://en.wikipedia.org/wiki/Gini_coefficient
- Certificate Transparency: https://certificate.transparency.dev/
- Event Sourcing Security: https://eventstore.com/blog/security-and-event-sourcing/
- Coercion-Resistant Voting: https://www.usenix.org/legacy/events/evt08/tech/full_papers/juels/juels.pdf
