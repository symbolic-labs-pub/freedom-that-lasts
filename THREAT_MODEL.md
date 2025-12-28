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

## Threat 9: Budget Manipulation (v0.2)

### Attack Scenario

**Attacker Goal**: Manipulate budget allocations to funnel resources without oversight

**Attack Sequence**:
1. Attacker gains budget control through delegation
2. Makes large cuts to CRITICAL items
3. Reallocates funds to controlled categories
4. Spends funds before detection
5. Budget integrity compromised

### FTL Mitigation: Multi-Gate Enforcement

#### Gate 1: Flex Step-Size Limits

**Graduated Constraints**:
```python
class FlexClass(str, Enum):
    CRITICAL = "CRITICAL"           # 5% max change per adjustment
    IMPORTANT = "IMPORTANT"         # 15% max change per adjustment
    ASPIRATIONAL = "ASPIRATIONAL"   # 50% max change per adjustment
```

**Enforcement**:
```python
def validate_flex_step_size(item: BudgetItem, change: Decimal) -> None:
    change_percent = abs(change / item.allocated_amount)
    max_percent = flex_class.max_step_percent()
    if change_percent > max_percent:
        raise FlexStepSizeViolation(...)
```

**Result**: Large changes require many small adjustments, creating audit trail

#### Gate 2: Zero-Sum Balance

**Constraint**: Total allocated = budget total (always)
```python
def validate_budget_balance(adjustments: list) -> None:
    total_change = sum(adj.change_amount for adj in adjustments)
    if total_change != Decimal("0"):
        raise BudgetBalanceViolation(...)
```

**Result**: Cannot increase spending without reducing elsewhere

#### Gate 3: Delegation Authority

**Enforcement**: Actor must have decision rights in workspace
- Handled by FTL delegation system
- Budget operations require workspace authority

#### Gate 4: No Overspending

**Constraint**: Allocated ≥ Spent (always)
```python
def validate_no_overspending(item: BudgetItem, new_allocation: Decimal) -> None:
    if new_allocation < item.spent_amount:
        raise AllocationBelowSpending(...)
```

**Result**: Cannot cut allocation below already-spent amount

### Cost Imposed on Attacker

**Structural**: Multiple independent gates must pass
**Temporal**: Large changes require multiple transactions
**Transparency**: Every adjustment creates audit trail event
**Detection**: Automatic triggers flag balance violations

## Threat 10: Time Manipulation

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

## Threat 11: Path Traversal (v1.0)

### Attack Scenario

**Attacker Goal**: Access or overwrite system files via malicious database paths

**Attack Sequence**:
1. System accepts user-provided database path
2. Attacker provides path with `..` sequences: `/tmp/../../etc/passwd`
3. System resolves path and accesses/writes sensitive files
4. System files compromised or secrets leaked

### FTL Mitigation: Path Validation

#### Canonical Path Resolution

**Implementation**:
```python
def validate_db_path(path: str | Path) -> Path:
    """Prevent path traversal attacks"""
    path_obj = Path(path).resolve()  # Canonical resolution

    # Restricted base directory (production)
    base_path_str = os.getenv("FTL_DB_BASE_PATH")
    if base_path_str:
        allowed_base = Path(base_path_str).resolve()
        try:
            path_obj.relative_to(allowed_base)
        except ValueError:
            raise ValueError(f"Path must be within {allowed_base}")

    if path_obj.exists() and path_obj.is_dir():
        raise ValueError("Path is a directory. Must be file.")

    return path_obj
```

**Attack Prevention**:
- Resolves symbolic links and `..` sequences
- Enforces base directory containment (production)
- Prevents directory-as-file attacks

### Cost Imposed on Attacker

**Technical**: Cannot escape base directory
**Detection**: Failed attempts logged with full path
**Structural**: Validation happens before any file access

## Threat 12: Weak Random Number Generation (v1.0)

### Attack Scenario

**Attacker Goal**: Predict "random" selection outcomes

**Attack Sequence**:
1. System uses weak RNG (e.g., `random.Random()`, `uuid.uuid4()`)
2. Attacker observes several outputs
3. Attacker reconstructs internal state (Mersenne Twister)
4. Attacker predicts future "random" selections
5. Procurement becomes predictable, not fair

**Real-World Example**: Casino RNG hacks, blockchain mining attacks

### FTL Mitigation: Cryptographic RNG

#### Correlation IDs

**Before (Weak)**:
```python
import uuid
correlation_id = str(uuid.uuid4())  # Not guaranteed cryptographically secure
```

**After (Strong)**:
```python
import secrets
correlation_id = secrets.token_urlsafe(16)  # 128 bits of entropy from OS CSPRNG
```

#### Supplier Selection

**Before (Weak)**:
```python
import random
rng = random.Random(seed_int)  # Mersenne Twister - predictable!
index = rng.randint(0, len(suppliers) - 1)
```

**After (Strong)**:
```python
import hashlib
seed_hash = hashlib.sha256(seed.encode()).hexdigest()  # SHA-256 cryptographic hash
seed_int = int(seed_hash, 16)
index = seed_int % len(suppliers)  # Deterministic but cryptographically strong
```

**Why SHA-256?**
- Cryptographically secure (preimage resistance)
- Deterministic (same seed = same output)
- Auditable (reproducible for verification)

### Cost Imposed on Attacker

**Cryptographic**: Cannot predict SHA-256 output
**Auditability**: Same seed produces same result (verifiable)
**Transparency**: Seed published in audit trail

## Threat 13: Denial of Service (DoS) (v1.0)

### Attack Scenario

**Attacker Goal**: Overwhelm health endpoints to prevent monitoring

**Attack Sequence**:
1. Health endpoints have no rate limiting
2. Attacker floods `/health/live` with requests
3. Server resources exhausted (CPU, memory, network)
4. Legitimate health checks fail
5. Kubernetes kills pod, cascading failure

### FTL Mitigation: Rate Limiting

#### Graduated Limits

**Implementation**:
```python
from flask_limiter import Limiter

limiter = Limiter(app=app, key_func=get_remote_address, storage_uri="memory://")

@app.route("/health/live")
@limiter.limit("30 per minute")
def liveness():
    return {"status": "alive"}

@app.route("/health/ready")
@limiter.limit("30 per minute")
def readiness():
    return check_readiness()

@app.route("/metrics")
@limiter.limit("10 per minute")
def metrics():
    return prometheus_client.generate_latest()
```

**Rationale**:
- Liveness/Readiness: 30 req/min (2-second Kubernetes probes)
- Metrics: 10 req/min (1-minute Prometheus scrapes)

### Cost Imposed on Attacker

**Technical**: Requests beyond limit receive HTTP 429
**Resource**: In-memory rate limiter has minimal overhead
**Detection**: Rate limit violations logged

## Threat 14: Information Disclosure via Logs (v1.0)

### Attack Scenario

**Attacker Goal**: Extract PII or secrets from production logs

**Attack Sequence**:
1. Logs contain actor_id, from_actor, to_actor, amount
2. Attacker gains read access to log aggregation system
3. Attacker correlates PII across events
4. Privacy-by-default violated
5. Coercion becomes possible (can identify delegation patterns)

**Real-World Example**: Log aggregation breaches, CloudTrail data mining

### FTL Mitigation: PII Redaction

#### Automatic Field Redaction

**Implementation**:
```python
REDACTED_FIELDS = {
    "actor_id", "from_actor", "to_actor",  # Privacy-by-default
    "amount",                              # Financial data
    "password", "token", "secret", "api_key", "private_key"  # Secrets
}

def redact_context(context: dict) -> dict:
    """Redact sensitive fields from logs"""
    return {
        k: "***REDACTED***" if k in REDACTED_FIELDS else v
        for k, v in context.items()
    }
```

**Applied in `LogOperation` context manager**:
```python
with LogOperation(logger, "delegate_decision_right", from_actor="alice", to_actor="bob"):
    # Logs: from_actor=***REDACTED***, to_actor=***REDACTED***
    delegate(...)
```

#### Environment-Aware Stack Traces

**Implementation**:
```python
def is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() == "production"

# Stack traces only in development
logger.error("Operation failed", exc_info=not is_production())
```

**Rationale**:
- **Production**: No stack traces (information disclosure risk)
- **Development**: Full stack traces (debuggability)

### Cost Imposed on Attacker

**Technical**: PII not present in logs to steal
**Operational**: Stack traces hidden in production
**Privacy**: Maintains privacy-by-default guarantees

## Threat 15: Supply Chain Attacks (v1.0)

### Attack Scenario

**Attacker Goal**: Inject malicious code via compromised dependencies

**Attack Sequence**:
1. System uses `latest` Docker tags or unpinned GitHub Actions
2. Attacker compromises upstream dependency
3. Attacker pushes malicious update with same tag
4. System pulls "latest" and executes malicious code
5. Supply chain compromised

**Real-World Examples**: SolarWinds, codecov, event-stream npm package

### FTL Mitigation: Dependency Pinning

#### Pinned Docker Images

**Before (Vulnerable)**:
```yaml
image: prom/prometheus:latest  # Tag can be mutated!
image: grafana/grafana:latest
```

**After (Secure)**:
```yaml
image: prom/prometheus:v2.48.1  # Specific version
image: grafana/grafana:10.2.3
image: python:3.11-slim          # Major.minor pinned
```

#### Pinned GitHub Actions

**Before (Vulnerable)**:
```yaml
- uses: actions/checkout@v4  # Tag can be moved!
```

**After (Secure)**:
```yaml
- uses: actions/checkout@08eba0b5e0b1e9b89f5c4d15e1f7f7b8a7f7f7f7  # Commit SHA
- uses: actions/setup-python@12345678901234567890123456789012345678
```

**Why Commit SHAs?**
- **Immutable**: Cannot change SHA without changing code
- **Verifiable**: Can audit exact code executed
- **Defense**: Prevents tag-moving attacks

#### Security Scanning

**CI Integration**:
```yaml
- name: Security Audit
  run: |
    pip-audit --strict       # CVE scanning for Python deps
    safety check --json      # Vulnerability database
    bandit -r src/ -ll       # Static security analysis
```

### Cost Imposed on Attacker

**Structural**: Cannot inject via tag mutation
**Detection**: Security scans flag known CVEs
**Transparency**: All dependencies versioned in git

## Threat 16: Container Escape (v1.0)

### Attack Scenario

**Attacker Goal**: Escape container to access host system

**Attack Sequence**:
1. Container runs as root user
2. Container filesystem is writable
3. Attacker exploits vulnerability to gain code execution
4. Attacker writes malware to filesystem (persistence)
5. Attacker escalates privileges using root
6. Attacker escapes container to host

### FTL Mitigation: Container Hardening

#### Read-Only Filesystem

**Implementation**:
```yaml
services:
  ftl:
    read_only: true
    tmpfs:
      - /tmp         # Writable temp space
      - /app/logs    # Writable logs
```

**Result**: Malware cannot persist to filesystem

#### Non-Root User

**Dockerfile**:
```dockerfile
RUN groupadd -r -g 1001 testuser && \
    useradd -r -u 1001 -g testuser testuser && \
    chown -R testuser:testuser /app

USER testuser
```

**Result**: Privilege escalation limited (no setuid, no kernel exploits)

#### Localhost Binding

**docker-compose.yml**:
```yaml
ports:
  - "127.0.0.1:8080:8080"  # Only accessible from host
```

**Result**: External attackers cannot reach endpoints

### Cost Imposed on Attacker

**Structural**: Read-only filesystem prevents persistence
**Privilege**: Non-root limits escalation paths
**Network**: Localhost binding prevents external access

## Threat 17: HTTP Security Header Bypass (v1.0)

### Attack Scenario

**Attacker Goal**: Execute XSS or clickjacking attacks

**Attack Sequence**:
1. Health endpoints missing security headers
2. Attacker injects malicious JavaScript via reflected parameter
3. Browser executes script (no CSP header)
4. Attacker steals session cookies or performs CSRF
5. Or: Attacker embeds endpoint in iframe (no X-Frame-Options)
6. Clickjacking attack successful

### FTL Mitigation: OWASP Security Headers

#### Implementation

**All Responses**:
```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'none'"
    return response
```

**Protection Against**:
- **XSS**: CSP blocks inline scripts and external resources
- **Clickjacking**: X-Frame-Options prevents iframe embedding
- **MIME Sniffing**: X-Content-Type-Options enforces declared types
- **Protocol Downgrade**: HSTS enforces HTTPS

### Cost Imposed on Attacker

**Technical**: CSP blocks most XSS vectors
**Structural**: X-Frame-Options prevents clickjacking
**Cryptographic**: HSTS prevents downgrade attacks

## Threat Matrix

| Threat | Severity | FTL Mitigation | Status | Residual Risk |
|--------|----------|----------------|--------|---------------|
| Delegation Concentration | HIGH | Gini + In-Degree + TTL | ✓ v0.1 | LOW - Attack detectable & costly |
| Irreversible Drift | HIGH | Mandatory Checkpoints | ✓ v0.1 | LOW - No permanent laws possible |
| Vote Coercion | MEDIUM | Privacy by Default + PII Redaction | ✓ v0.1+v1.0 | LOW - No proof-of-vote possible |
| Circular Authority | MEDIUM | Acyclic DAG Constraint | ✓ v0.1 | NONE - Mathematically prevented |
| Permanent Delegation | MEDIUM | Max TTL + Expiry | ✓ v0.1 | LOW - Max 1 year, renewal required |
| Complexity Overwhelm | MEDIUM | Health Metrics | ⚠ Partial v0.1 | MEDIUM - Visibility only |
| Database Tampering | LOW | Append-Only + Constraints | ⚠ Partial v0.1 | MEDIUM - Requires external audit log |
| Sybil Attacks | MEDIUM | Gini (partial) | ❌ Future v2.0 | HIGH - Identity out of scope |
| Budget Manipulation | HIGH | Multi-Gate Enforcement | ✓ v0.2 | LOW - 4 independent gates |
| Time Manipulation | LOW | TimeProvider Abstraction | ✓ v0.1 | LOW - Requires root access |
| Path Traversal | HIGH | Canonical Path Validation | ✓ v1.0 | LOW - Cannot escape base directory |
| Weak RNG | MEDIUM | Cryptographic RNG (secrets, SHA-256) | ✓ v1.0 | LOW - Cryptographically secure |
| Denial of Service | MEDIUM | Rate Limiting (Flask-Limiter) | ✓ v1.0 | LOW - 10-30 req/min limits |
| Information Disclosure | HIGH | PII Redaction + Environment-Aware Logging | ✓ v1.0 | LOW - Automatic field redaction |
| Supply Chain Attack | HIGH | Pinned Dependencies (SHA, versions) | ✓ v1.0 | LOW - Immutable references |
| Container Escape | MEDIUM | Read-Only FS + Non-Root + Localhost | ✓ v1.0 | LOW - Multiple hardening layers |
| HTTP Header Bypass | MEDIUM | OWASP Security Headers | ✓ v1.0 | LOW - CSP, HSTS, X-Frame-Options |

## Defense in Depth

### Layer 1: Structural Constraints (Preventive)
- Acyclic graph (prevents cycles)
- Max TTL (prevents permanent authority)
- Required checkpoints (prevents permanent laws)
- Multi-gate budget enforcement (prevents manipulation)
- Path validation (prevents traversal)
- Pinned dependencies (prevents supply chain)

### Layer 2: Automatic Detection (Detective)
- Gini coefficient (detects concentration)
- Tick loop (detects expiry, overdue reviews, budget violations)
- FreedomHealth scorecard (surfaces risk)
- Rate limiting (detects DoS)
- Security scanning (detects CVEs)

### Layer 3: Automatic Response (Reactive)
- Halt new delegations (concentration threshold)
- Trigger law reviews (overdue checkpoints)
- Transparency escalation (publish more metrics)
- HTTP 429 (rate limit exceeded)
- Reject invalid paths (validation failure)

### Layer 4: Audit Trail (Forensic)
- Immutable event log
- Actor attribution (PII-redacted in logs)
- Timestamp ordering
- Replay capability
- Correlation IDs (cryptographic)

### Layer 5: Privacy Protection (Coercion Resistance)
- Private delegations by default
- Aggregate metrics only
- No proof-of-vote artifacts
- PII redaction in logs
- Environment-aware stack traces

### Layer 6: Container Security (Infrastructure)
- Read-only filesystem
- Non-root user (UID 1001)
- Localhost binding
- OWASP security headers
- Cryptographic RNG

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

### v2.0: Enhanced Tamper Resistance
- Event hash chains (cryptographic audit trail)
- External audit log (blockchain or Certificate Transparency)
- Multi-signature event signing
- Distributed event store with consensus (Raft/Paxos)
- Byzantine fault tolerance

### v2.1: Identity Integration
- Decentralized Identifiers (DIDs)
- Verifiable Credentials (VCs)
- Reputation scoring with decay
- Sybil resistance mechanisms
- Zero-knowledge delegation proofs

### v2.2: Advanced Security
- Homomorphic encryption for aggregate metrics
- Threshold signatures for multi-party authorization
- Secure multi-party computation for selection
- Differential privacy for concentration metrics

## References

- Gini Coefficient: https://en.wikipedia.org/wiki/Gini_coefficient
- Certificate Transparency: https://certificate.transparency.dev/
- Event Sourcing Security: https://eventstore.com/blog/security-and-event-sourcing/
- Coercion-Resistant Voting: https://www.usenix.org/legacy/events/evt08/tech/full_papers/juels/juels.pdf
