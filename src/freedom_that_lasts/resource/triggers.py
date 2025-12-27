"""
Resource & Procurement Triggers

Automatic reflexes that monitor procurement health and emit warning/halt events.
Triggers run during tick loop to detect anti-capture violations.

Fun fact: The concept of "triggers" in databases was invented by Don Chamberlin
and Raymond Boyce at IBM in the 1970s - we're using them to trigger democracy
safeguards against procurement capture!
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from freedom_that_lasts.kernel.events import Event, create_event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.resource import events
from freedom_that_lasts.resource.models import TenderStatus
from freedom_that_lasts.resource.selection import (
    compute_gini_coefficient,
    compute_supplier_shares,
)


def evaluate_empty_feasible_set_trigger(
    evaluating_tenders: list[dict[str, Any]],
    now: datetime,
) -> list[Event]:
    """
    Check all EVALUATING tenders for empty feasible sets

    Empty feasible set indicates:
    - Requirements too strict, OR
    - Supplier base insufficient

    Should trigger law review to adjust requirements or build supplier capacity.

    Args:
        evaluating_tenders: List of tenders in EVALUATING status
        now: Current timestamp

    Returns:
        List of EmptyFeasibleSetDetected events (one per empty tender)

    Example:
        >>> tenders = [
        ...     {
        ...         "tender_id": "t1",
        ...         "law_id": "law-1",
        ...         "feasible_suppliers": [],  # Empty!
        ...         "requirements": [{"capability_type": "ISO27001"}],
        ...     }
        ... ]
        >>> events = evaluate_empty_feasible_set_trigger(tenders, datetime.now())
        >>> len(events)
        1
    """
    trigger_events = []

    for tender in evaluating_tenders:
        tender_id = tender.get("tender_id")
        law_id = tender.get("law_id")
        feasible_suppliers = tender.get("feasible_suppliers", [])

        # Check if feasible set is empty
        if not feasible_suppliers or len(feasible_suppliers) == 0:
            # Emit warning event
            event_payload = events.EmptyFeasibleSetDetected(
                tender_id=tender_id,
                law_id=law_id,
                detected_at=now,
                requirements_summary={
                    "requirements": tender.get("requirements", []),
                    "required_capacity": tender.get("required_capacity"),
                    "excluded_count": len(
                        tender.get("excluded_suppliers_with_reasons", [])
                    ),
                },
                action_required="Review requirements or build supplier capacity",
            ).model_dump(mode="json")

            trigger_events.append(
                create_event(
                    event_id=generate_id(),
                    stream_id=tender_id,
                    stream_type="Tender",
                    event_type="EmptyFeasibleSetDetected",
                    occurred_at=now,
                    actor_id="system",
                    command_id="trigger",  # Trigger event, not from command
                    payload=event_payload,
                    version=1,  # Trigger events don't update stream version
                )
            )

    return trigger_events


def evaluate_supplier_concentration_trigger(
    supplier_registry: dict[str, Any],
    tender_registry: dict[str, Any],
    safety_policy: SafetyPolicy,
    now: datetime,
) -> list[Event]:
    """
    Monitor supplier concentration (anti-capture safeguard)

    Computes:
    - Total procurement value
    - Each supplier's share
    - Gini coefficient (inequality measure)

    Emits:
    - SupplierConcentrationWarning if share > warn threshold (default 20%)
    - SupplierConcentrationHalt if share > halt threshold (default 35%)

    When halted, supplier is excluded from rotation until diversification achieved.

    Args:
        supplier_registry: Supplier registry dictionary (from projection)
        tender_registry: Tender registry dictionary (from projection)
        safety_policy: Safety policy with concentration thresholds
        now: Current timestamp

    Returns:
        List of concentration warning/halt events

    Example:
        >>> registry = {
        ...     "suppliers": {
        ...         "s1": {"supplier_id": "s1", "total_value_awarded": Decimal("400000")},
        ...         "s2": {"supplier_id": "s2", "total_value_awarded": Decimal("100000")},
        ...     }
        ... }
        >>> policy = SafetyPolicy(supplier_share_warn_threshold=0.20)
        >>> events = evaluate_supplier_concentration_trigger(
        ...     registry, {}, policy, datetime.now()
        ... )
        >>> # s1 has 80% share (400k/500k) - exceeds 20% threshold
        >>> len(events) > 0
        True
    """
    trigger_events = []

    # Extract suppliers from registry
    suppliers = list(supplier_registry.get("suppliers", {}).values())

    if not suppliers or len(suppliers) == 0:
        return []

    # Compute supplier shares
    shares = compute_supplier_shares(suppliers)

    if not shares:
        return []

    # Compute total procurement value
    total_value = sum(
        s.get("total_value_awarded", Decimal("0")) for s in suppliers
    )

    # Compute Gini coefficient
    gini = compute_gini_coefficient(shares)

    # Find supplier with highest share
    top_supplier_id = max(shares.keys(), key=lambda sid: shares[sid])
    top_supplier_share = shares[top_supplier_id]

    # Get thresholds from safety policy
    warn_threshold = safety_policy.supplier_share_warn_threshold
    halt_threshold = safety_policy.supplier_share_halt_threshold

    # Check for concentration violations
    # We check the top supplier against thresholds

    # HALT threshold (critical - excludes supplier from rotation)
    if top_supplier_share > halt_threshold:
        event_payload = events.SupplierConcentrationHalt(
            detected_at=now,
            total_procurement_value=total_value,
            supplier_shares=shares,
            gini_coefficient=gini,
            halted_supplier_id=top_supplier_id,
            supplier_share=top_supplier_share,
            critical_threshold_exceeded=halt_threshold,
        ).model_dump(mode="json")

        trigger_events.append(
            create_event(
                event_id=generate_id(),
                stream_id=top_supplier_id,
                stream_type="Supplier",
                event_type="SupplierConcentrationHalt",
                occurred_at=now,
                actor_id="system",
                command_id="trigger",
                payload=event_payload,
                version=1,  # Trigger events don't update stream version
            )
        )

    # WARN threshold (monitoring - no exclusion yet)
    elif top_supplier_share > warn_threshold:
        event_payload = events.SupplierConcentrationWarning(
            detected_at=now,
            total_procurement_value=total_value,
            supplier_shares=shares,
            gini_coefficient=gini,
            top_supplier_id=top_supplier_id,
            top_supplier_share=top_supplier_share,
            threshold_exceeded=warn_threshold,
        ).model_dump(mode="json")

        trigger_events.append(
            create_event(
                event_id=generate_id(),
                stream_id=top_supplier_id,
                stream_type="Supplier",
                event_type="SupplierConcentrationWarning",
                occurred_at=now,
                actor_id="system",
                command_id="trigger",
                payload=event_payload,
                version=1,  # Trigger events don't update stream version
            )
        )

    return trigger_events


def evaluate_all_procurement_triggers(
    supplier_registry: dict[str, Any],
    tender_registry: dict[str, Any],
    safety_policy: SafetyPolicy,
    now: datetime,
) -> list[Event]:
    """
    Evaluate all procurement triggers in one pass

    Convenience function for tick loop integration.

    Args:
        supplier_registry: Supplier registry projection
        tender_registry: Tender registry projection
        safety_policy: Safety policy
        now: Current timestamp

    Returns:
        List of all triggered events
    """
    all_events = []

    # Get evaluating tenders
    tenders = tender_registry.get("tenders", {}).values()
    evaluating_tenders = [
        t for t in tenders if t.get("status") == TenderStatus.EVALUATING
    ]

    # Check empty feasible sets
    all_events.extend(evaluate_empty_feasible_set_trigger(evaluating_tenders, now))

    # Check supplier concentration
    all_events.extend(
        evaluate_supplier_concentration_trigger(
            supplier_registry, tender_registry, safety_policy, now
        )
    )

    return all_events
