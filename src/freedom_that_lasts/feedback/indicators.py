"""
Risk Indicators - Concentration metrics and FreedomHealth computation

These functions compute the key metrics that detect power entrenchment,
irreversible drift, and other threats to freedom.

Fun fact: The Gini coefficient was originally designed to measure income
inequality, but it works perfectly for measuring decision-making power
concentration too!
"""

from datetime import datetime

from freedom_that_lasts.feedback.models import (
    ConcentrationMetrics,
    FreedomHealthScore,
    LawReviewHealth,
    RiskLevel,
)
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy


def compute_gini_coefficient(in_degrees: list[int]) -> float:
    """
    Compute Gini coefficient for delegation concentration

    The Gini coefficient measures inequality in a distribution:
    - 0.0 = Perfect equality (everyone has same in-degree)
    - 1.0 = Perfect inequality (one person has all delegations)

    Formula: G = (2 * sum(i * x[i])) / (n * sum(x)) - (n+1) / n
    where x is sorted in ascending order

    Args:
        in_degrees: List of in-degree counts for all actors

    Returns:
        Gini coefficient between 0.0 and 1.0
    """
    if not in_degrees or sum(in_degrees) == 0:
        return 0.0

    # Sort in ascending order
    sorted_degrees = sorted(in_degrees)
    n = len(sorted_degrees)
    total = sum(sorted_degrees)

    # Compute Gini using the standard formula
    cumsum = 0.0
    for i, degree in enumerate(sorted_degrees, start=1):
        cumsum += i * degree

    gini = (2 * cumsum) / (n * total) - (n + 1) / n
    return max(0.0, min(1.0, gini))  # Clamp to [0, 1]


def compute_concentration_metrics(
    in_degree_map: dict[str, int],
) -> ConcentrationMetrics:
    """
    Compute delegation concentration metrics

    Args:
        in_degree_map: Map of actor_id -> incoming delegation count

    Returns:
        ConcentrationMetrics with Gini coefficient and other stats
    """
    if not in_degree_map:
        return ConcentrationMetrics(
            gini_coefficient=0.0,
            max_in_degree=0,
            total_active_delegations=0,
            unique_delegates=0,
        )

    in_degrees = list(in_degree_map.values())
    gini = compute_gini_coefficient(in_degrees)
    max_in_degree = max(in_degrees) if in_degrees else 0
    total = sum(in_degrees)
    unique = len([d for d in in_degrees if d > 0])

    return ConcentrationMetrics(
        gini_coefficient=gini,
        max_in_degree=max_in_degree,
        total_active_delegations=total,
        unique_delegates=unique,
    )


def compute_law_review_health(
    total_active: int,
    overdue_count: int,
    upcoming_7d: int,
    upcoming_30d: int,
) -> LawReviewHealth:
    """
    Compute law review checkpoint health

    Args:
        total_active: Total active laws
        overdue_count: Number of laws with overdue reviews
        upcoming_7d: Reviews due in next 7 days
        upcoming_30d: Reviews due in next 30 days

    Returns:
        LawReviewHealth metrics
    """
    return LawReviewHealth(
        total_active_laws=total_active,
        overdue_reviews=overdue_count,
        upcoming_reviews_7d=upcoming_7d,
        upcoming_reviews_30d=upcoming_30d,
    )


def evaluate_risk_level(
    concentration: ConcentrationMetrics,
    law_health: LawReviewHealth,
    policy: SafetyPolicy,
) -> tuple[RiskLevel, list[str]]:
    """
    Evaluate overall system risk level

    Combines concentration and law review metrics to determine
    whether system is GREEN, YELLOW, or RED.

    Args:
        concentration: Delegation concentration metrics
        law_health: Law review health metrics
        policy: Safety policy with thresholds

    Returns:
        Tuple of (RiskLevel, reasons)
    """
    reasons: list[str] = []
    is_halt = False
    is_warn = False

    # Check delegation concentration - HALT thresholds
    if concentration.gini_coefficient >= policy.delegation_gini_halt:
        is_halt = True
        reasons.append(
            f"delegation_gini_halt: {concentration.gini_coefficient:.3f} >= {policy.delegation_gini_halt}"
        )

    if concentration.max_in_degree >= policy.delegation_in_degree_halt:
        is_halt = True
        reasons.append(
            f"delegation_in_degree_halt: {concentration.max_in_degree} >= {policy.delegation_in_degree_halt}"
        )

    # Check delegation concentration - WARN thresholds
    if concentration.gini_coefficient >= policy.delegation_gini_warn:
        is_warn = True
        reasons.append(
            f"delegation_gini_warn: {concentration.gini_coefficient:.3f} >= {policy.delegation_gini_warn}"
        )

    if concentration.max_in_degree >= policy.delegation_in_degree_warn:
        is_warn = True
        reasons.append(
            f"delegation_in_degree_warn: {concentration.max_in_degree} >= {policy.delegation_in_degree_warn}"
        )

    # Check law review health
    if law_health.overdue_reviews > 0:
        is_warn = True
        reasons.append(f"law_reviews_overdue: {law_health.overdue_reviews} laws")

    # Determine overall level
    if is_halt:
        return RiskLevel.RED, reasons
    elif is_warn:
        return RiskLevel.YELLOW, reasons
    else:
        return RiskLevel.GREEN, ["All safeguards within normal bounds"]


def compute_freedom_health(
    in_degree_map: dict[str, int],
    total_active_laws: int,
    overdue_reviews: int,
    upcoming_7d: int,
    upcoming_30d: int,
    policy: SafetyPolicy,
    now: datetime,
) -> FreedomHealthScore:
    """
    Compute complete FreedomHealth scorecard

    This is the main health indicator shown to operators.

    Args:
        in_degree_map: Delegation in-degree distribution
        total_active_laws: Total active laws
        overdue_reviews: Overdue review count
        upcoming_7d: Reviews due in 7 days
        upcoming_30d: Reviews due in 30 days
        policy: Safety policy
        now: Current time

    Returns:
        Complete FreedomHealthScore
    """
    concentration = compute_concentration_metrics(in_degree_map)
    law_health = compute_law_review_health(
        total_active_laws, overdue_reviews, upcoming_7d, upcoming_30d
    )
    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    return FreedomHealthScore(
        risk_level=risk_level,
        concentration=concentration,
        law_review_health=law_health,
        reasons=reasons,
        computed_at=now,
    )
