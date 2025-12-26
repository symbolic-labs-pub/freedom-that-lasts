"""
Law Module Invariants - Constitutional constraints that MUST hold

Invariants are the non-negotiable rules that enforce anti-tyranny safeguards.
They are pure functions (no side effects) that validate state transitions.

Fun fact: Invariants are called "invariants" because they must remain true
(invariant) across all possible system states. Violating an invariant is
like violating the laws of physics - the system prevents it!
"""

from datetime import datetime, timedelta
from typing import Any

from freedom_that_lasts.kernel.errors import (
    DelegationCycleDetected,
    InvalidCheckpointSchedule,
    InvariantViolation,
    TTLExceedsMaximum,
    WorkspaceNotFound,
)
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.law.models import DelegationEdge


# Delegation Invariants


def validate_delegation_ttl(ttl_days: int, policy: SafetyPolicy) -> None:
    """
    Enforce maximum delegation TTL from safety policy

    This prevents permanent authority accumulation - all delegations
    must be renewed periodically, preventing silent entrenchment.

    Args:
        ttl_days: Requested TTL
        policy: Current safety policy

    Raises:
        TTLExceedsMaximum: If TTL exceeds policy maximum
    """
    if ttl_days > policy.max_delegation_ttl_days:
        raise TTLExceedsMaximum(ttl_days, policy.max_delegation_ttl_days)


def validate_acyclic_delegation(
    existing_edges: list[DelegationEdge],
    from_actor: str,
    to_actor: str,
    now: datetime,
) -> None:
    """
    Ensure delegation graph remains acyclic (no cycles)

    Cycles in delegation create "power loops" where authority
    circulates with no clear source. This is a fundamental
    anti-tyranny safeguard.

    Algorithm: DFS-based cycle detection
    - Build adjacency list from active delegations
    - Check if adding new edge would create cycle
    - O(V+E) time complexity

    Args:
        existing_edges: Current delegation edges
        from_actor: Who is delegating
        to_actor: Who receives delegation
        now: Current time (for checking expiry)

    Raises:
        DelegationCycleDetected: If new edge would create a cycle

    Fun fact: This is the same algorithm used in Git to prevent
    circular branch dependencies!
    """
    # Build adjacency list from active delegations
    adjacency: dict[str, list[str]] = {}

    for edge in existing_edges:
        if edge.is_active and edge.expires_at > now:
            if edge.from_actor not in adjacency:
                adjacency[edge.from_actor] = []
            adjacency[edge.from_actor].append(edge.to_actor)

    # Check if adding new edge would create cycle using DFS
    def has_path(start: str, target: str, visited: set[str]) -> bool:
        """DFS to check if there's a path from start to target"""
        if start == target:
            return True
        if start in visited:
            return False

        visited.add(start)

        for neighbor in adjacency.get(start, []):
            if has_path(neighbor, target, visited):
                return True

        return False

    # If there's already a path from to_actor to from_actor,
    # adding from_actor -> to_actor would create a cycle
    if has_path(to_actor, from_actor, set()):
        raise DelegationCycleDetected(from_actor, to_actor)


def validate_workspace_exists(
    workspace_id: str, workspace_registry: dict[str, Any]
) -> None:
    """
    Verify workspace exists before creating delegation/law

    Args:
        workspace_id: Workspace to check
        workspace_registry: Current workspace registry state

    Raises:
        WorkspaceNotFound: If workspace doesn't exist
    """
    if workspace_id not in workspace_registry:
        raise WorkspaceNotFound(workspace_id)


# Law Invariants


def validate_checkpoint_schedule(
    checkpoints: list[int], policy: SafetyPolicy
) -> None:
    """
    Ensure law checkpoint schedule meets minimum requirements

    Mandatory checkpoints prevent laws from drifting into
    irreversibility without review. The policy defines minimum
    checkpoint frequency.

    Args:
        checkpoints: Proposed checkpoint schedule (days after activation)
        policy: Current safety policy

    Raises:
        InvalidCheckpointSchedule: If schedule doesn't meet minimums

    Fun fact: Exponentially-spaced checkpoints (30, 90, 180, 365)
    are ideal because they allow rapid iteration early while
    stabilizing over time!
    """
    if not checkpoints:
        raise InvalidCheckpointSchedule(checkpoints, policy.law_min_checkpoint_schedule)

    # Checkpoints must be positive and sorted
    if not all(cp > 0 for cp in checkpoints):
        raise InvariantViolation("All checkpoints must be positive")

    if checkpoints != sorted(checkpoints):
        raise InvariantViolation("Checkpoints must be in ascending order")

    # Use the policy's validation method
    if not policy.validate_checkpoint_schedule(checkpoints):
        raise InvalidCheckpointSchedule(checkpoints, policy.law_min_checkpoint_schedule)


def compute_next_checkpoint(
    activated_at: datetime,
    checkpoints: list[int],
    current_checkpoint_index: int,
) -> tuple[datetime | None, int]:
    """
    Compute the next checkpoint datetime

    Args:
        activated_at: When law was activated
        checkpoints: Checkpoint schedule (days after activation)
        current_checkpoint_index: Index of current checkpoint

    Returns:
        Tuple of (next_checkpoint_datetime, next_checkpoint_index)
        Returns (None, -1) if no more checkpoints
    """
    if current_checkpoint_index >= len(checkpoints):
        return None, -1

    next_checkpoint_days = checkpoints[current_checkpoint_index]
    next_checkpoint_at = activated_at + timedelta(days=next_checkpoint_days)

    return next_checkpoint_at, current_checkpoint_index


def validate_law_activation(
    workspace_id: str,
    checkpoints: list[int],
    workspace_registry: dict[str, Any],
    policy: SafetyPolicy,
) -> None:
    """
    Validate all preconditions for law activation

    Combines multiple invariant checks for clean activation workflow.

    Args:
        workspace_id: Where law applies
        checkpoints: Checkpoint schedule
        workspace_registry: Current workspace state
        policy: Current safety policy

    Raises:
        WorkspaceNotFound: If workspace doesn't exist
        InvalidCheckpointSchedule: If checkpoints invalid
    """
    validate_workspace_exists(workspace_id, workspace_registry)
    validate_checkpoint_schedule(checkpoints, policy)


# Delegation Graph Analysis (for concentration metrics)


def compute_in_degrees(edges: list[DelegationEdge], now: datetime) -> dict[str, int]:
    """
    Compute in-degree for each actor (how many delegations they receive)

    High in-degree indicates concentration of authority - a potential
    tyranny risk when thresholds are exceeded.

    Args:
        edges: Current delegation edges
        now: Current time (for filtering active delegations)

    Returns:
        Map of actor -> in-degree count

    Fun fact: In-degree distribution follows a power law in most
    delegation networks - a few actors accumulate most authority!
    """
    in_degrees: dict[str, int] = {}

    for edge in edges:
        if edge.is_active and edge.expires_at > now:
            in_degrees[edge.to_actor] = in_degrees.get(edge.to_actor, 0) + 1

    return in_degrees


def compute_graph_depth(
    edges: list[DelegationEdge], now: datetime
) -> dict[str, int]:
    """
    Compute maximum delegation chain depth for each actor

    Depth measures how many delegation "hops" an actor is from
    the root authority. Very deep chains can indicate complex
    delegation structures that may be hard to audit.

    Args:
        edges: Current delegation edges
        now: Current time

    Returns:
        Map of actor -> maximum depth
    """
    # Build adjacency list
    adjacency: dict[str, list[str]] = {}
    all_actors: set[str] = set()

    for edge in edges:
        if edge.is_active and edge.expires_at > now:
            if edge.from_actor not in adjacency:
                adjacency[edge.from_actor] = []
            adjacency[edge.from_actor].append(edge.to_actor)
            all_actors.add(edge.from_actor)
            all_actors.add(edge.to_actor)

    # Compute depth via BFS from each potential root
    depths: dict[str, int] = {}

    def bfs_depth(start: str) -> dict[str, int]:
        """BFS to compute depth from a starting node"""
        visited = {start: 0}
        queue = [start]

        while queue:
            current = queue.pop(0)
            current_depth = visited[current]

            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited[neighbor] = current_depth + 1
                    queue.append(neighbor)

        return visited

    # Find roots (actors with no incoming edges)
    has_incoming = {edge.to_actor for edge in edges if edge.is_active}
    roots = all_actors - has_incoming

    # Compute depths from all roots
    for root in roots:
        root_depths = bfs_depth(root)
        for actor, depth in root_depths.items():
            depths[actor] = max(depths.get(actor, 0), depth)

    return depths


def find_cycles(edges: list[DelegationEdge], now: datetime) -> list[list[str]]:
    """
    Find all cycles in the delegation graph (should be empty!)

    This is a diagnostic function - if it returns any cycles,
    the acyclic invariant has been violated (a bug).

    Args:
        edges: Current delegation edges
        now: Current time

    Returns:
        List of cycles (each cycle is a list of actors)

    Fun fact: Finding all cycles is NP-hard, but finding any cycle
    is linear time using DFS!
    """
    # Build adjacency list
    adjacency: dict[str, list[str]] = {}

    for edge in edges:
        if edge.is_active and edge.expires_at > now:
            if edge.from_actor not in adjacency:
                adjacency[edge.from_actor] = []
            adjacency[edge.from_actor].append(edge.to_actor)

    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> bool:
        """DFS with recursion stack to detect cycles"""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    # Run DFS from each unvisited node
    for node in adjacency:
        if node not in visited:
            dfs(node)

    return cycles
