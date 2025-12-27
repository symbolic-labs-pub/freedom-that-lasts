"""
Constitutional Supplier Selection Mechanisms

No discretion, no subjective evaluation - algorithmic and auditable selection.
Three mechanisms: rotation (anti-monopolization), random (fairness), hybrid (balanced).

Fun fact: The ancient Athenian democracy (508-322 BCE) used a randomization device
called a 'kleroterion' to select officials by lottery - preventing corruption through
randomness. We're bringing that wisdom forward with cryptographic verifiability!
"""

import hashlib
import random
from decimal import Decimal
from typing import Any


def select_by_rotation(
    feasible_suppliers: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Select supplier by rotation (load balancing)

    Selects supplier with lowest total_value_awarded (least loaded).
    Breaks ties by supplier_id (lexicographic order for determinism).

    This prevents monopolization - work distributed across suppliers.

    Args:
        feasible_suppliers: List of supplier dictionaries

    Returns:
        Selected supplier dictionary

    Raises:
        ValueError: If feasible_suppliers is empty

    Example:
        >>> suppliers = [
        ...     {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
        ...     {"supplier_id": "s2", "total_value_awarded": Decimal("50000")},
        ... ]
        >>> selected = select_by_rotation(suppliers)
        >>> selected["supplier_id"]
        's2'  # Lower total_value_awarded
    """
    if not feasible_suppliers or len(feasible_suppliers) == 0:
        raise ValueError("Cannot select from empty feasible set")

    # Sort by total_value_awarded (ascending), then supplier_id (for determinism)
    sorted_suppliers = sorted(
        feasible_suppliers,
        key=lambda s: (
            s.get("total_value_awarded", Decimal("0")),
            s["supplier_id"],
        ),
    )

    return sorted_suppliers[0]


def select_by_random(
    feasible_suppliers: list[dict[str, Any]], seed: str
) -> dict[str, Any]:
    """
    Select supplier by auditable randomness

    Uses seed to deterministically select from feasible set.
    Same seed + same feasible set = same selection (reproducible).

    Seed should be hash of (tender_id + evaluation_time + nonce) for auditability.

    Args:
        feasible_suppliers: List of supplier dictionaries
        seed: Random seed for selection

    Returns:
        Selected supplier dictionary

    Raises:
        ValueError: If feasible_suppliers is empty

    Example:
        >>> suppliers = [{"supplier_id": "s1"}, {"supplier_id": "s2"}]
        >>> selected = select_by_random(suppliers, "hash-abc123")
        >>> # Deterministic - same seed = same result
        >>> selected2 = select_by_random(suppliers, "hash-abc123")
        >>> selected["supplier_id"] == selected2["supplier_id"]
        True
    """
    if not feasible_suppliers or len(feasible_suppliers) == 0:
        raise ValueError("Cannot select from empty feasible set")

    # Sort by supplier_id for deterministic ordering
    sorted_suppliers = sorted(feasible_suppliers, key=lambda s: s["supplier_id"])

    # Use seed to generate deterministic random index
    # Hash seed to get numeric value
    seed_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    seed_int = int(seed_hash, 16)

    # Use seeded random to select
    rng = random.Random(seed_int)
    index = rng.randint(0, len(sorted_suppliers) - 1)

    return sorted_suppliers[index]


def select_by_rotation_with_random(
    feasible_suppliers: list[dict[str, Any]], seed: str, rotation_threshold: float = 0.1
) -> dict[str, Any]:
    """
    Hybrid selection: rotation among low-loaded suppliers, then random

    1. Find suppliers within rotation_threshold of minimum load
    2. Randomly select from that subset

    Balances load distribution (rotation) with fairness (randomness).

    Args:
        feasible_suppliers: List of supplier dictionaries
        seed: Random seed for final selection
        rotation_threshold: Percentage threshold for "low-loaded" (default 10%)

    Returns:
        Selected supplier dictionary

    Raises:
        ValueError: If feasible_suppliers is empty

    Example:
        >>> suppliers = [
        ...     {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
        ...     {"supplier_id": "s2", "total_value_awarded": Decimal("105000")},
        ...     {"supplier_id": "s3", "total_value_awarded": Decimal("200000")},
        ... ]
        >>> selected = select_by_rotation_with_random(suppliers, "seed", 0.1)
        >>> selected["supplier_id"] in ["s1", "s2"]  # Both within 10% of min
        True
    """
    if not feasible_suppliers or len(feasible_suppliers) == 0:
        raise ValueError("Cannot select from empty feasible set")

    # Find minimum total_value_awarded
    min_value = min(
        s.get("total_value_awarded", Decimal("0")) for s in feasible_suppliers
    )

    # Calculate threshold (minimum + rotation_threshold%)
    threshold = min_value * (Decimal("1") + Decimal(str(rotation_threshold)))

    # Filter to suppliers within threshold (low-loaded subset)
    low_loaded = [
        s
        for s in feasible_suppliers
        if s.get("total_value_awarded", Decimal("0")) <= threshold
    ]

    # If no suppliers in threshold (shouldn't happen), fall back to all
    if not low_loaded:
        low_loaded = feasible_suppliers

    # Randomly select from low-loaded subset
    return select_by_random(low_loaded, seed)


def compute_supplier_shares(
    suppliers: list[dict[str, Any]],
) -> dict[str, float]:
    """
    Compute each supplier's share of total procurement value

    Used for concentration monitoring and anti-capture safeguards.

    Args:
        suppliers: List of all supplier dictionaries from registry

    Returns:
        Dictionary mapping supplier_id → share (0.0-1.0)

    Example:
        >>> suppliers = [
        ...     {"supplier_id": "s1", "total_value_awarded": Decimal("300000")},
        ...     {"supplier_id": "s2", "total_value_awarded": Decimal("200000")},
        ...     {"supplier_id": "s3", "total_value_awarded": Decimal("500000")},
        ... ]
        >>> shares = compute_supplier_shares(suppliers)
        >>> shares["s3"]  # 500000 / 1000000 = 0.5
        0.5
    """
    if not suppliers or len(suppliers) == 0:
        return {}

    # Calculate total procurement value
    total_value = sum(
        s.get("total_value_awarded", Decimal("0")) for s in suppliers
    )

    if total_value == 0:
        # No contracts awarded yet - equal shares
        equal_share = 1.0 / len(suppliers)
        return {s["supplier_id"]: equal_share for s in suppliers}

    # Calculate each supplier's share
    shares = {}
    for supplier in suppliers:
        supplier_value = supplier.get("total_value_awarded", Decimal("0"))
        share = float(supplier_value) / float(total_value)
        shares[supplier["supplier_id"]] = share

    return shares


def compute_gini_coefficient(shares: dict[str, float]) -> float:
    """
    Compute Gini coefficient of supplier concentration

    Gini coefficient measures inequality:
    - 0.0 = perfect equality (all suppliers have equal share)
    - 1.0 = perfect inequality (one supplier has everything)

    Typical thresholds:
    - < 0.3: Low concentration (healthy competition)
    - 0.3-0.5: Moderate concentration (monitor)
    - > 0.5: High concentration (anti-capture alert)

    Args:
        shares: Dictionary mapping supplier_id → share (0.0-1.0)

    Returns:
        Gini coefficient (0.0-1.0)

    Fun fact: The Gini coefficient was developed by Italian statistician
    Corrado Gini in 1912 to measure wealth inequality - we're using it
    to prevent procurement monopolies!
    """
    if not shares or len(shares) == 0:
        return 0.0

    if len(shares) == 1:
        return 0.0  # Single supplier = no inequality to measure

    # Get share values sorted ascending
    sorted_shares = sorted(shares.values())
    n = len(sorted_shares)

    # Gini coefficient formula:
    # G = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n + 1) / n
    # where x_i are shares sorted ascending
    cumulative_share = sum((i + 1) * share for i, share in enumerate(sorted_shares))
    total_share = sum(sorted_shares)

    if total_share == 0:
        return 0.0

    gini = (2 * cumulative_share) / (n * total_share) - (n + 1) / n

    return max(0.0, min(1.0, gini))  # Clamp to [0, 1]


def apply_reputation_threshold(
    feasible_suppliers: list[dict[str, Any]], min_reputation: float
) -> list[dict[str, Any]]:
    """
    Filter suppliers by minimum reputation threshold

    Reputation threshold is pass/fail (min-gate), not ranking.
    Prevents low-performing suppliers from being selected.

    Args:
        feasible_suppliers: List of supplier dictionaries
        min_reputation: Minimum reputation score required (0.0-1.0)

    Returns:
        Filtered list of suppliers meeting reputation threshold

    Example:
        >>> suppliers = [
        ...     {"supplier_id": "s1", "reputation_score": 0.95},
        ...     {"supplier_id": "s2", "reputation_score": 0.55},  # Below threshold
        ...     {"supplier_id": "s3", "reputation_score": 0.80},
        ... ]
        >>> filtered = apply_reputation_threshold(suppliers, 0.60)
        >>> len(filtered)
        2  # s1 and s3 pass, s2 fails
    """
    if min_reputation < 0.0 or min_reputation > 1.0:
        raise ValueError("min_reputation must be between 0.0 and 1.0")

    return [
        s
        for s in feasible_suppliers
        if s.get("reputation_score", 0.5) >= min_reputation
    ]


def get_rotation_state(suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Get current rotation state for audit trail

    Returns supplier loads for transparency and auditability.

    Args:
        suppliers: List of supplier dictionaries

    Returns:
        Dictionary with rotation state:
        {
            "supplier_loads": {supplier_id: total_value_awarded},
            "min_load": Decimal,
            "max_load": Decimal,
            "shares": {supplier_id: share}
        }
    """
    if not suppliers:
        return {
            "supplier_loads": {},
            "min_load": Decimal("0"),
            "max_load": Decimal("0"),
            "shares": {},
        }

    supplier_loads = {
        s["supplier_id"]: s.get("total_value_awarded", Decimal("0"))
        for s in suppliers
    }

    loads = list(supplier_loads.values())
    min_load = min(loads) if loads else Decimal("0")
    max_load = max(loads) if loads else Decimal("0")

    shares = compute_supplier_shares(suppliers)

    return {
        "supplier_loads": supplier_loads,
        "min_load": str(min_load),  # Convert to string for JSON serialization
        "max_load": str(max_load),
        "shares": shares,
    }
