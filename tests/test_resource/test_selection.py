"""
Tests for Constitutional Supplier Selection Mechanisms

No discretion, no subjective evaluation - algorithmic and auditable selection.
Three mechanisms: rotation (anti-monopolization), random (fairness), hybrid (balanced).

Fun fact: The ancient Athenian democracy (508-322 BCE) used a randomization device
called a 'kleroterion' to select officials by lottery - we're bringing that wisdom
forward with cryptographic verifiability!
"""

from decimal import Decimal

import pytest

from freedom_that_lasts.resource.selection import (
    select_by_rotation,
    select_by_random,
    select_by_rotation_with_random,
    compute_supplier_shares,
    compute_gini_coefficient,
    apply_reputation_threshold,
    get_rotation_state,
)
from tests.helpers import create_balanced_suppliers_for_rotation


# ==============================================================================
# Rotation Selection Tests (Load Balancing)
# ==============================================================================


def test_select_by_rotation_lowest_load() -> None:
    """Test rotation selects supplier with lowest total_value_awarded"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("150000")},
        {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},  # Lowest!
        {"supplier_id": "s3", "total_value_awarded": Decimal("200000")},
    ]

    selected = select_by_rotation(suppliers)

    assert selected["supplier_id"] == "s2"
    assert selected["total_value_awarded"] == Decimal("100000")


def test_select_by_rotation_tie_breaking() -> None:
    """Test rotation tie-breaks by supplier_id (lexicographic order)"""
    suppliers = [
        {"supplier_id": "s3", "total_value_awarded": Decimal("100000")},
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},  # Same load, but s1 < s3
        {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},
    ]

    selected = select_by_rotation(suppliers)

    # Tie-breaking by supplier_id - s1 comes first lexicographically
    assert selected["supplier_id"] == "s1"


def test_select_by_rotation_zero_load() -> None:
    """Test rotation with suppliers having zero load"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("0")},  # New supplier
        {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},
        {"supplier_id": "s3", "total_value_awarded": Decimal("0")},  # New supplier
    ]

    selected = select_by_rotation(suppliers)

    # Should select first zero-load supplier by ID (s1)
    assert selected["supplier_id"] == "s1"


def test_select_by_rotation_missing_total_value_defaults_zero() -> None:
    """Test rotation treats missing total_value_awarded as zero"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
        {"supplier_id": "s2"},  # Missing total_value_awarded!
    ]

    selected = select_by_rotation(suppliers)

    # s2 should be selected (missing value defaults to 0)
    assert selected["supplier_id"] == "s2"


def test_select_by_rotation_empty_list_raises() -> None:
    """Test rotation with empty supplier list raises ValueError"""
    with pytest.raises(ValueError, match="Cannot select from empty feasible set"):
        select_by_rotation([])


def test_select_by_rotation_single_supplier() -> None:
    """Test rotation with single supplier"""
    suppliers = [{"supplier_id": "s1", "total_value_awarded": Decimal("100000")}]

    selected = select_by_rotation(suppliers)

    assert selected["supplier_id"] == "s1"


# ==============================================================================
# Random Selection Tests (Deterministic Seed-Based)
# ==============================================================================


def test_select_by_random_deterministic() -> None:
    """Test random selection is deterministic (same seed = same result)"""
    suppliers = [
        {"supplier_id": "s1"},
        {"supplier_id": "s2"},
        {"supplier_id": "s3"},
    ]

    seed = "test-seed-12345"

    selected1 = select_by_random(suppliers, seed)
    selected2 = select_by_random(suppliers, seed)
    selected3 = select_by_random(suppliers, seed)

    # All selections should be identical
    assert selected1["supplier_id"] == selected2["supplier_id"]
    assert selected2["supplier_id"] == selected3["supplier_id"]


def test_select_by_random_different_seeds() -> None:
    """Test different seeds produce different selections (probabilistically)"""
    suppliers = [
        {"supplier_id": "s1"},
        {"supplier_id": "s2"},
        {"supplier_id": "s3"},
        {"supplier_id": "s4"},
        {"supplier_id": "s5"},
    ]

    # With 5 suppliers, different seeds should yield different results
    selected1 = select_by_random(suppliers, "seed-1")["supplier_id"]
    selected2 = select_by_random(suppliers, "seed-2")["supplier_id"]
    selected3 = select_by_random(suppliers, "seed-3")["supplier_id"]
    selected4 = select_by_random(suppliers, "seed-4")["supplier_id"]
    selected5 = select_by_random(suppliers, "seed-5")["supplier_id"]

    # At least some should be different (probabilistically very likely)
    all_selections = {selected1, selected2, selected3, selected4, selected5}
    assert len(all_selections) > 1  # Not all the same


def test_select_by_random_sorted_by_supplier_id() -> None:
    """Test random selection uses deterministic supplier ordering (by ID)"""
    suppliers_ordered = [
        {"supplier_id": "s1"},
        {"supplier_id": "s2"},
        {"supplier_id": "s3"},
    ]

    suppliers_unordered = [
        {"supplier_id": "s3"},
        {"supplier_id": "s1"},
        {"supplier_id": "s2"},
    ]

    seed = "consistent-seed"

    selected_ordered = select_by_random(suppliers_ordered, seed)
    selected_unordered = select_by_random(suppliers_unordered, seed)

    # Same selection regardless of input order (deterministic sorting)
    assert selected_ordered["supplier_id"] == selected_unordered["supplier_id"]


def test_select_by_random_empty_list_raises() -> None:
    """Test random selection with empty list raises ValueError"""
    with pytest.raises(ValueError, match="Cannot select from empty feasible set"):
        select_by_random([], "seed")


def test_select_by_random_single_supplier() -> None:
    """Test random selection with single supplier"""
    suppliers = [{"supplier_id": "s1"}]

    selected = select_by_random(suppliers, "any-seed")

    assert selected["supplier_id"] == "s1"


def test_select_by_random_sha256_modulo() -> None:
    """Test random selection uses SHA-256 hash modulo for index calculation"""
    # Known seed should produce consistent index
    suppliers = [{"supplier_id": f"s{i}"} for i in range(10)]

    seed = "known-seed-abc"
    selected = select_by_random(suppliers, seed)

    # Should be deterministic based on SHA-256(seed) % 10
    # We can't predict exact result without knowing hash, but we can verify consistency
    selected_again = select_by_random(suppliers, seed)
    assert selected["supplier_id"] == selected_again["supplier_id"]


# ==============================================================================
# Hybrid Selection Tests (Rotation + Random)
# ==============================================================================


def test_select_by_rotation_with_random_filters_low_loaded() -> None:
    """Test hybrid selection filters to low-loaded suppliers first"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},  # Min
        {"supplier_id": "s2", "total_value_awarded": Decimal("105000")},  # Within 10%
        {"supplier_id": "s3", "total_value_awarded": Decimal("110000")},  # Within 10%
        {"supplier_id": "s4", "total_value_awarded": Decimal("200000")},  # Too high!
    ]

    # Default threshold is 10%
    # Min = 100000, threshold = 100000 * 1.1 = 110000
    # s1, s2, s3 should be in low-loaded set, s4 excluded

    selected = select_by_rotation_with_random(suppliers, "test-seed", rotation_threshold=0.1)

    # Should be one of s1, s2, or s3 (not s4)
    assert selected["supplier_id"] in ["s1", "s2", "s3"]


def test_select_by_rotation_with_random_deterministic() -> None:
    """Test hybrid selection is deterministic for same seed"""
    suppliers = create_balanced_suppliers_for_rotation(5)

    seed = "hybrid-seed-123"

    selected1 = select_by_rotation_with_random(suppliers, seed)
    selected2 = select_by_rotation_with_random(suppliers, seed)

    # Same seed = same selection
    assert selected1["supplier_id"] == selected2["supplier_id"]


def test_select_by_rotation_with_random_custom_threshold() -> None:
    """Test hybrid selection with custom rotation threshold"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},  # Min
        {"supplier_id": "s2", "total_value_awarded": Decimal("125000")},  # Within 25%
        {"supplier_id": "s3", "total_value_awarded": Decimal("150000")},  # Beyond 25%
    ]

    # Threshold 25%: Min = 100000, threshold = 100000 * 1.25 = 125000
    # s1 and s2 should be in low-loaded set, s3 excluded

    selected = select_by_rotation_with_random(suppliers, "seed", rotation_threshold=0.25)

    assert selected["supplier_id"] in ["s1", "s2"]


def test_select_by_rotation_with_random_all_zero_load() -> None:
    """Test hybrid selection when all suppliers have zero load"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("0")},
        {"supplier_id": "s2", "total_value_awarded": Decimal("0")},
        {"supplier_id": "s3", "total_value_awarded": Decimal("0")},
    ]

    # Min = 0, threshold = 0 * 1.1 = 0
    # All suppliers are at threshold (0 <= 0)

    selected = select_by_rotation_with_random(suppliers, "seed")

    # All should be in low-loaded set
    assert selected["supplier_id"] in ["s1", "s2", "s3"]


def test_select_by_rotation_with_random_empty_list_raises() -> None:
    """Test hybrid selection with empty list raises ValueError"""
    with pytest.raises(ValueError, match="Cannot select from empty feasible set"):
        select_by_rotation_with_random([], "seed")


def test_select_by_rotation_with_random_fallback_to_all() -> None:
    """Test hybrid selection falls back to all suppliers if low-loaded set is empty"""
    # This shouldn't happen in practice (min is always in threshold), but test defensive code
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
    ]

    selected = select_by_rotation_with_random(suppliers, "seed")

    # Should select the only supplier
    assert selected["supplier_id"] == "s1"


# ==============================================================================
# Supplier Shares Tests
# ==============================================================================


def test_compute_supplier_shares_basic() -> None:
    """Test supplier shares computation for basic scenario"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("300000")},
        {"supplier_id": "s2", "total_value_awarded": Decimal("200000")},
        {"supplier_id": "s3", "total_value_awarded": Decimal("500000")},
    ]

    shares = compute_supplier_shares(suppliers)

    # Total = 1000000
    assert shares["s1"] == pytest.approx(0.3)  # 300000 / 1000000
    assert shares["s2"] == pytest.approx(0.2)  # 200000 / 1000000
    assert shares["s3"] == pytest.approx(0.5)  # 500000 / 1000000


def test_compute_supplier_shares_zero_total() -> None:
    """Test supplier shares when total value is zero (equal shares)"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("0")},
        {"supplier_id": "s2", "total_value_awarded": Decimal("0")},
        {"supplier_id": "s3", "total_value_awarded": Decimal("0")},
    ]

    shares = compute_supplier_shares(suppliers)

    # Equal shares when no contracts awarded
    assert shares["s1"] == pytest.approx(1.0 / 3)
    assert shares["s2"] == pytest.approx(1.0 / 3)
    assert shares["s3"] == pytest.approx(1.0 / 3)


def test_compute_supplier_shares_empty_list() -> None:
    """Test supplier shares with empty supplier list"""
    shares = compute_supplier_shares([])

    assert shares == {}


def test_compute_supplier_shares_missing_total_value() -> None:
    """Test supplier shares treats missing total_value_awarded as zero"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("500000")},
        {"supplier_id": "s2"},  # Missing total_value_awarded
    ]

    shares = compute_supplier_shares(suppliers)

    # Total = 500000, s2 treated as 0
    assert shares["s1"] == pytest.approx(1.0)
    assert shares["s2"] == pytest.approx(0.0)


# ==============================================================================
# Gini Coefficient Tests
# ==============================================================================


def test_compute_gini_coefficient_perfect_equality() -> None:
    """Test Gini coefficient for perfect equality (all equal shares)"""
    shares = {
        "s1": 0.25,
        "s2": 0.25,
        "s3": 0.25,
        "s4": 0.25,
    }

    gini = compute_gini_coefficient(shares)

    # Perfect equality = 0.0
    assert gini == pytest.approx(0.0, abs=0.01)


def test_compute_gini_coefficient_perfect_inequality() -> None:
    """Test Gini coefficient for perfect inequality (one has everything)"""
    shares = {
        "s1": 1.0,
        "s2": 0.0,
        "s3": 0.0,
        "s4": 0.0,
    }

    gini = compute_gini_coefficient(shares)

    # Perfect inequality approaches 1.0
    # With 4 suppliers where 1 has everything: Gini = (n-1)/n = 3/4 = 0.75
    assert gini == pytest.approx(0.75, abs=0.01)


def test_compute_gini_coefficient_moderate_inequality() -> None:
    """Test Gini coefficient for moderate inequality"""
    shares = {
        "s1": 0.5,  # One supplier has half
        "s2": 0.2,
        "s3": 0.2,
        "s4": 0.1,
    }

    gini = compute_gini_coefficient(shares)

    # Moderate inequality - between 0 and 1
    assert 0.0 < gini < 1.0
    # Typical threshold: 0.3-0.5 is moderate concentration
    assert gini > 0.2  # Should show some inequality


def test_compute_gini_coefficient_single_supplier() -> None:
    """Test Gini coefficient with single supplier (no inequality to measure)"""
    shares = {"s1": 1.0}

    gini = compute_gini_coefficient(shares)

    # Single supplier = no inequality (can't compare to others)
    assert gini == 0.0


def test_compute_gini_coefficient_empty_dict() -> None:
    """Test Gini coefficient with empty shares dictionary"""
    gini = compute_gini_coefficient({})

    assert gini == 0.0


def test_compute_gini_coefficient_zero_total() -> None:
    """Test Gini coefficient when total share is zero"""
    shares = {
        "s1": 0.0,
        "s2": 0.0,
        "s3": 0.0,
    }

    gini = compute_gini_coefficient(shares)

    # Zero total = no inequality to measure
    assert gini == 0.0


def test_compute_gini_coefficient_two_suppliers() -> None:
    """Test Gini coefficient with two suppliers (edge case)"""
    shares = {
        "s1": 0.8,
        "s2": 0.2,
    }

    gini = compute_gini_coefficient(shares)

    # With 2 suppliers using Gini formula: G = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n + 1) / n
    # Sorted: [0.2, 0.8], cumulative_share = 1*0.2 + 2*0.8 = 1.8
    # G = (2 * 1.8) / (2 * 1.0) - (2 + 1) / 2 = 1.8 - 1.5 = 0.3
    assert gini == pytest.approx(0.3, abs=0.01)


# ==============================================================================
# Reputation Threshold Tests
# ==============================================================================


def test_apply_reputation_threshold_basic() -> None:
    """Test reputation threshold filters suppliers below minimum"""
    suppliers = [
        {"supplier_id": "s1", "reputation_score": 0.95},  # Pass
        {"supplier_id": "s2", "reputation_score": 0.55},  # Fail
        {"supplier_id": "s3", "reputation_score": 0.80},  # Pass
        {"supplier_id": "s4", "reputation_score": 0.59},  # Fail
    ]

    filtered = apply_reputation_threshold(suppliers, min_reputation=0.60)

    # Only s1 and s3 should pass
    assert len(filtered) == 2
    filtered_ids = [s["supplier_id"] for s in filtered]
    assert "s1" in filtered_ids
    assert "s3" in filtered_ids


def test_apply_reputation_threshold_exact_boundary() -> None:
    """Test reputation threshold at exact boundary (inclusive)"""
    suppliers = [
        {"supplier_id": "s1", "reputation_score": 0.60},  # Exactly at threshold
        {"supplier_id": "s2", "reputation_score": 0.59},  # Just below
    ]

    filtered = apply_reputation_threshold(suppliers, min_reputation=0.60)

    # s1 should pass (>= threshold), s2 should fail
    assert len(filtered) == 1
    assert filtered[0]["supplier_id"] == "s1"


def test_apply_reputation_threshold_missing_reputation_defaults() -> None:
    """Test reputation threshold treats missing reputation_score as 0.5"""
    suppliers = [
        {"supplier_id": "s1", "reputation_score": 0.80},
        {"supplier_id": "s2"},  # Missing reputation_score
    ]

    filtered = apply_reputation_threshold(suppliers, min_reputation=0.60)

    # s1 passes, s2 gets default 0.5 which fails threshold 0.60
    assert len(filtered) == 1
    assert filtered[0]["supplier_id"] == "s1"


def test_apply_reputation_threshold_all_pass() -> None:
    """Test reputation threshold when all suppliers pass"""
    suppliers = [
        {"supplier_id": "s1", "reputation_score": 0.95},
        {"supplier_id": "s2", "reputation_score": 0.85},
        {"supplier_id": "s3", "reputation_score": 0.75},
    ]

    filtered = apply_reputation_threshold(suppliers, min_reputation=0.50)

    # All should pass
    assert len(filtered) == 3


def test_apply_reputation_threshold_none_pass() -> None:
    """Test reputation threshold when no suppliers pass"""
    suppliers = [
        {"supplier_id": "s1", "reputation_score": 0.45},
        {"supplier_id": "s2", "reputation_score": 0.40},
        {"supplier_id": "s3", "reputation_score": 0.35},
    ]

    filtered = apply_reputation_threshold(suppliers, min_reputation=0.60)

    # None should pass
    assert len(filtered) == 0


def test_apply_reputation_threshold_invalid_range_raises() -> None:
    """Test reputation threshold with invalid min_reputation raises ValueError"""
    suppliers = [{"supplier_id": "s1", "reputation_score": 0.75}]

    with pytest.raises(ValueError, match="min_reputation must be between 0.0 and 1.0"):
        apply_reputation_threshold(suppliers, min_reputation=1.5)

    with pytest.raises(ValueError, match="min_reputation must be between 0.0 and 1.0"):
        apply_reputation_threshold(suppliers, min_reputation=-0.5)


# ==============================================================================
# Rotation State Tests (Audit Trail)
# ==============================================================================


def test_get_rotation_state_basic() -> None:
    """Test rotation state returns supplier loads and shares"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
        {"supplier_id": "s2", "total_value_awarded": Decimal("200000")},
        {"supplier_id": "s3", "total_value_awarded": Decimal("300000")},
    ]

    state = get_rotation_state(suppliers)

    # Check supplier loads
    assert state["supplier_loads"]["s1"] == Decimal("100000")
    assert state["supplier_loads"]["s2"] == Decimal("200000")
    assert state["supplier_loads"]["s3"] == Decimal("300000")

    # Check min/max (converted to strings for JSON serialization)
    assert state["min_load"] == "100000"
    assert state["max_load"] == "300000"

    # Check shares
    assert state["shares"]["s1"] == pytest.approx(1.0 / 6)
    assert state["shares"]["s2"] == pytest.approx(2.0 / 6)
    assert state["shares"]["s3"] == pytest.approx(3.0 / 6)


def test_get_rotation_state_empty_suppliers() -> None:
    """Test rotation state with no suppliers"""
    state = get_rotation_state([])

    assert state["supplier_loads"] == {}
    assert state["shares"] == {}
    # Note: With empty list, min() and max() raise ValueError, so implementation sets defaults
    assert "min_load" in state
    assert "max_load" in state


def test_get_rotation_state_missing_total_value() -> None:
    """Test rotation state treats missing total_value_awarded as zero"""
    suppliers = [
        {"supplier_id": "s1", "total_value_awarded": Decimal("100000")},
        {"supplier_id": "s2"},  # Missing total_value_awarded
    ]

    state = get_rotation_state(suppliers)

    assert state["supplier_loads"]["s1"] == Decimal("100000")
    assert state["supplier_loads"]["s2"] == Decimal("0")
    assert state["min_load"] == "0"
    assert state["max_load"] == "100000"
