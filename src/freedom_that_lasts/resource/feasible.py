"""
Feasible Set Computation - Binary Requirement Matching

Core algorithm for constitutional procurement: binary yes/no matching (no scoring, no weighting).
Supplier either meets ALL requirements or doesn't - no subjective evaluation.

Fun fact: Binary logic dates back to ancient Indian mathematician Pingala (300 BCE)
who developed the first binary number system for Sanskrit poetry metrics - we're using
it to prevent procurement corruption 2300 years later!
"""

from datetime import datetime
from typing import Any


def compute_feasible_set(
    suppliers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    required_capacity: dict[str, Any] | None,
    evaluation_time: datetime,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Compute feasible set via binary requirement matching

    Feasible set F = { supplier | ∀ requirement ∈ requirements:
                       supplier.has_capability(requirement) ∧
                       supplier.capacity ≥ required_capacity ∧
                       evidence_valid }

    NO scoring, NO weighting, NO subjective evaluation - just binary yes/no.

    Args:
        suppliers: List of supplier dictionaries from registry
        requirements: List of requirement dictionaries from tender
        required_capacity: Overall capacity requirements (optional)
        evaluation_time: Time to check evidence expiration against

    Returns:
        Tuple of (feasible_supplier_ids[], excluded_with_reasons[])
        where excluded_with_reasons = [{"supplier_id": str, "reasons": [str]}]

    Example:
        >>> suppliers = [{"supplier_id": "s1", "capabilities": {...}}]
        >>> requirements = [{"capability_type": "ISO27001", "mandatory": True}]
        >>> feasible, excluded = compute_feasible_set(suppliers, requirements, None, now)
        >>> print(feasible)  # ["s1"] if s1 has ISO27001, [] otherwise
    """
    feasible_suppliers: list[str] = []
    excluded_suppliers: list[dict[str, Any]] = []

    # Check each supplier against ALL requirements (universal quantification)
    for supplier in suppliers:
        supplier_id = supplier["supplier_id"]
        reasons: list[str] = []

        # Check ALL requirements (binary AND - all must be true)
        for requirement in requirements:
            capability_type = requirement["capability_type"]
            mandatory = requirement.get("mandatory", True)

            # Get supplier's capability claim
            capabilities = supplier.get("capabilities", {})

            if capability_type not in capabilities:
                if mandatory:
                    reasons.append(f"Missing required capability: {capability_type}")
                continue

            claim = capabilities[capability_type]

            # Check claim validity at evaluation time
            valid_from = claim.get("valid_from")
            valid_until = claim.get("valid_until")

            # Convert strings to datetime for comparison
            if valid_from and isinstance(valid_from, str):
                valid_from = datetime.fromisoformat(valid_from)
            if valid_until and isinstance(valid_until, str):
                valid_until = datetime.fromisoformat(valid_until)

            # Normalize timezone awareness for comparison
            # Make all datetimes timezone-naive for comparison
            eval_time_naive = evaluation_time.replace(tzinfo=None) if evaluation_time.tzinfo else evaluation_time
            valid_from_naive = valid_from.replace(tzinfo=None) if (valid_from and valid_from.tzinfo) else valid_from
            valid_until_naive = valid_until.replace(tzinfo=None) if (valid_until and valid_until.tzinfo) else valid_until

            if valid_from_naive and eval_time_naive < valid_from_naive:
                if mandatory:
                    reasons.append(
                        f"Capability {capability_type} not yet valid "
                        f"(valid from {valid_from})"
                    )
                continue

            if valid_until_naive and eval_time_naive > valid_until_naive:
                if mandatory:
                    reasons.append(
                        f"Capability {capability_type} expired "
                        f"(valid until {valid_until})"
                    )
                continue

            # Check evidence not expired
            evidence = claim.get("evidence", [])
            expired_evidence = []
            for ev in evidence:
                ev_valid_until = ev.get("valid_until")
                # Convert string to datetime if needed
                if ev_valid_until and isinstance(ev_valid_until, str):
                    ev_valid_until = datetime.fromisoformat(ev_valid_until)
                # Normalize timezone for comparison
                ev_valid_until_naive = ev_valid_until.replace(tzinfo=None) if (ev_valid_until and ev_valid_until.tzinfo) else ev_valid_until
                if ev_valid_until_naive and eval_time_naive > ev_valid_until_naive:
                    expired_evidence.append(ev["evidence_id"])

            if expired_evidence:
                if mandatory:
                    reasons.append(
                        f"Capability {capability_type} has expired evidence: "
                        f"{', '.join(expired_evidence)}"
                    )
                continue

            # Check evidence verification status
            verified = claim.get("verified", False)
            if not verified:
                if mandatory:
                    reasons.append(
                        f"Capability {capability_type} evidence not yet verified"
                    )
                continue

            # Check minimum capacity requirements (if specified for this requirement)
            min_capacity = requirement.get("min_capacity")
            if min_capacity:
                claim_capacity = claim.get("capacity")
                if not claim_capacity:
                    if mandatory:
                        reasons.append(
                            f"Capability {capability_type} missing capacity data "
                            f"(required: {min_capacity})"
                        )
                    continue

                # Check each capacity constraint
                capacity_met = True
                for capacity_key, min_value in min_capacity.items():
                    actual_value = claim_capacity.get(capacity_key)
                    if actual_value is None:
                        if mandatory:
                            reasons.append(
                                f"Capability {capability_type} missing capacity metric: "
                                f"{capacity_key}"
                            )
                        capacity_met = False
                        break

                    # Simple comparison for numeric values
                    # In practice, this should be type-aware (units, etc.)
                    try:
                        if float(actual_value) < float(min_value):
                            if mandatory:
                                reasons.append(
                                    f"Capability {capability_type} insufficient capacity: "
                                    f"{capacity_key}={actual_value} < {min_value}"
                                )
                            capacity_met = False
                            break
                    except (ValueError, TypeError):
                        # Non-numeric comparison - do string comparison
                        if str(actual_value) != str(min_value):
                            if mandatory:
                                reasons.append(
                                    f"Capability {capability_type} capacity mismatch: "
                                    f"{capacity_key}={actual_value} != {min_value}"
                                )
                            capacity_met = False
                            break

                if not capacity_met:
                    continue

        # Check overall required capacity (tender-level, not per-requirement)
        if required_capacity:
            # Check supplier's aggregate capacity across all capabilities
            # This is a simplified check - in practice, capacity aggregation
            # would be more sophisticated (e.g., parallel vs sequential work)
            for capacity_key, min_value in required_capacity.items():
                # Find maximum capacity for this metric across all capabilities
                max_capacity = None
                for claim in capabilities.values():
                    if claim.get("capacity") and capacity_key in claim["capacity"]:
                        capacity_value = claim["capacity"][capacity_key]
                        try:
                            capacity_float = float(capacity_value)
                            if max_capacity is None or capacity_float > max_capacity:
                                max_capacity = capacity_float
                        except (ValueError, TypeError):
                            pass

                if max_capacity is None:
                    reasons.append(
                        f"Supplier missing required capacity metric: {capacity_key}"
                    )
                elif max_capacity < float(min_value):
                    reasons.append(
                        f"Insufficient overall capacity: {capacity_key}={max_capacity} < {min_value}"
                    )

        # Decision: feasible if NO mandatory requirement violations
        if not reasons:
            feasible_suppliers.append(supplier_id)
        else:
            excluded_suppliers.append({"supplier_id": supplier_id, "reasons": reasons})

    return feasible_suppliers, excluded_suppliers


def check_supplier_meets_requirement(
    supplier: dict[str, Any],
    requirement: dict[str, Any],
    evaluation_time: datetime,
) -> tuple[bool, str | None]:
    """
    Check if single supplier meets single requirement

    Helper function for testing and debugging.

    Args:
        supplier: Supplier dictionary
        requirement: Requirement dictionary
        evaluation_time: Time to check against

    Returns:
        Tuple of (meets_requirement, reason_if_not)
    """
    capability_type = requirement["capability_type"]
    capabilities = supplier.get("capabilities", {})

    if capability_type not in capabilities:
        return False, f"Missing capability: {capability_type}"

    claim = capabilities[capability_type]

    # Check validity period
    valid_from = claim.get("valid_from")
    valid_until = claim.get("valid_until")

    if valid_from and evaluation_time < valid_from:
        return False, f"Capability not yet valid (valid from {valid_from})"

    if valid_until and evaluation_time > valid_until:
        return False, f"Capability expired (valid until {valid_until})"

    # Check evidence expiration
    evidence = claim.get("evidence", [])
    for ev in evidence:
        ev_valid_until = ev.get("valid_until")
        if ev_valid_until and evaluation_time > ev_valid_until:
            return False, f"Evidence {ev['evidence_id']} expired"

    # Check verification
    if not claim.get("verified", False):
        return False, "Evidence not yet verified"

    # Check capacity
    min_capacity = requirement.get("min_capacity")
    if min_capacity:
        claim_capacity = claim.get("capacity")
        if not claim_capacity:
            return False, "Missing capacity data"

        for capacity_key, min_value in min_capacity.items():
            actual_value = claim_capacity.get(capacity_key)
            if actual_value is None:
                return False, f"Missing capacity metric: {capacity_key}"

            try:
                if float(actual_value) < float(min_value):
                    return (
                        False,
                        f"Insufficient capacity: {capacity_key}={actual_value} < {min_value}",
                    )
            except (ValueError, TypeError):
                if str(actual_value) != str(min_value):
                    return (
                        False,
                        f"Capacity mismatch: {capacity_key}={actual_value} != {min_value}",
                    )

    return True, None
