"""
Tests for Feedback Indicators - Concentration metrics and health computation

These tests verify that we correctly compute Gini coefficients,
concentration metrics, and overall risk levels.
"""

from datetime import datetime, timezone

import pytest

from freedom_that_lasts.feedback.indicators import (
    compute_concentration_metrics,
    compute_freedom_health,
    compute_gini_coefficient,
    evaluate_risk_level,
)
from freedom_that_lasts.feedback.models import RiskLevel
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy


def test_gini_coefficient_perfect_equality() -> None:
    """Test Gini coefficient with perfect equality"""
    # Everyone has same in-degree
    in_degrees = [10, 10, 10, 10, 10]
    gini = compute_gini_coefficient(in_degrees)
    assert gini == pytest.approx(0.0, abs=0.01)


def test_gini_coefficient_perfect_inequality() -> None:
    """Test Gini coefficient with perfect inequality"""
    # One person has everything
    in_degrees = [0, 0, 0, 0, 100]
    gini = compute_gini_coefficient(in_degrees)
    assert gini >= 0.8  # Very high concentration


def test_gini_coefficient_moderate_inequality() -> None:
    """Test Gini coefficient with moderate inequality"""
    # Some concentration but not extreme
    in_degrees = [5, 10, 15, 20, 50]
    gini = compute_gini_coefficient(in_degrees)
    assert 0.2 < gini < 0.5


def test_gini_coefficient_empty() -> None:
    """Test Gini coefficient with no data"""
    gini = compute_gini_coefficient([])
    assert gini == 0.0


def test_compute_concentration_metrics() -> None:
    """Test concentration metrics computation"""
    in_degree_map = {
        "alice": 5,
        "bob": 15,
        "charlie": 30,
        "dave": 10,
    }

    metrics = compute_concentration_metrics(in_degree_map)

    assert metrics.total_active_delegations == 60
    assert metrics.max_in_degree == 30
    assert metrics.unique_delegates == 4
    assert 0.0 <= metrics.gini_coefficient <= 1.0


def test_compute_concentration_metrics_empty() -> None:
    """Test concentration metrics with no delegations"""
    metrics = compute_concentration_metrics({})

    assert metrics.total_active_delegations == 0
    assert metrics.max_in_degree == 0
    assert metrics.unique_delegates == 0
    assert metrics.gini_coefficient == 0.0


def test_evaluate_risk_level_green() -> None:
    """Test risk level evaluation - GREEN (healthy)"""
    policy = SafetyPolicy()

    # Low concentration
    in_degree_map = {"alice": 5, "bob": 5, "charlie": 5}
    concentration = compute_concentration_metrics(in_degree_map)

    # No law issues
    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=0, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.GREEN
    assert "All safeguards within normal bounds" in reasons


def test_evaluate_risk_level_yellow_gini_warn() -> None:
    """Test risk level evaluation - YELLOW due to Gini warning"""
    policy = SafetyPolicy(delegation_gini_warn=0.5)

    # Moderate concentration that triggers warning
    in_degree_map = {"alice": 5, "bob": 10, "charlie": 50, "dave": 2}
    concentration = compute_concentration_metrics(in_degree_map)

    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=0, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.YELLOW
    assert any("delegation_gini_warn" in r for r in reasons)


def test_evaluate_risk_level_yellow_in_degree_warn() -> None:
    """Test risk level evaluation - YELLOW due to in-degree warning"""
    policy = SafetyPolicy(delegation_in_degree_warn=20)

    # Someone has high in-degree
    in_degree_map = {"alice": 5, "bob": 25, "charlie": 10}
    concentration = compute_concentration_metrics(in_degree_map)

    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=0, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.YELLOW
    assert any("delegation_in_degree_warn" in r for r in reasons)


def test_evaluate_risk_level_yellow_overdue_reviews() -> None:
    """Test risk level evaluation - YELLOW due to overdue reviews"""
    policy = SafetyPolicy()

    # Low concentration
    in_degree_map = {"alice": 5, "bob": 5}
    concentration = compute_concentration_metrics(in_degree_map)

    # But we have overdue reviews
    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=3, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.YELLOW
    assert any("law_reviews_overdue" in r for r in reasons)


def test_evaluate_risk_level_red_gini_halt() -> None:
    """Test risk level evaluation - RED due to Gini halt"""
    policy = SafetyPolicy(delegation_gini_halt=0.6)

    # Extreme concentration
    in_degree_map = {"alice": 2, "bob": 3, "charlie": 100}
    concentration = compute_concentration_metrics(in_degree_map)

    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=0, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.RED
    assert any("delegation_gini_halt" in r for r in reasons)


def test_evaluate_risk_level_red_in_degree_halt() -> None:
    """Test risk level evaluation - RED due to in-degree halt"""
    policy = SafetyPolicy(delegation_in_degree_halt=50)

    # Someone has extreme in-degree
    in_degree_map = {"alice": 5, "bob": 60, "charlie": 10}
    concentration = compute_concentration_metrics(in_degree_map)

    from freedom_that_lasts.feedback.indicators import compute_law_review_health

    law_health = compute_law_review_health(
        total_active=10, overdue_count=0, upcoming_7d=2, upcoming_30d=5
    )

    risk_level, reasons = evaluate_risk_level(concentration, law_health, policy)

    assert risk_level == RiskLevel.RED
    assert any("delegation_in_degree_halt" in r for r in reasons)


def test_compute_freedom_health() -> None:
    """Test complete FreedomHealth computation"""
    policy = SafetyPolicy()
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    in_degree_map = {"alice": 10, "bob": 15, "charlie": 20}

    health = compute_freedom_health(
        in_degree_map=in_degree_map,
        total_active_laws=10,
        overdue_reviews=0,
        upcoming_7d=2,
        upcoming_30d=5,
        policy=policy,
        now=now,
    )

    assert health.risk_level in [RiskLevel.GREEN, RiskLevel.YELLOW, RiskLevel.RED]
    assert health.concentration.total_active_delegations == 45
    assert health.law_review_health.total_active_laws == 10
    assert health.computed_at == now
