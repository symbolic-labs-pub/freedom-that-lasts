"""
Trigger Evaluation - Automatic Anti-Tyranny Reflexes

Triggers are automatic responses to dangerous conditions.
They evaluate system state and emit reflex events (warnings/halts).

This is the "immune system" - it detects threats and responds
automatically without requiring human intervention.

Fun fact: These triggers are inspired by the body's autonomic nervous
system - reflexes that protect you before you consciously think about it!
"""

from datetime import datetime

from freedom_that_lasts.feedback.indicators import compute_concentration_metrics
from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider
from freedom_that_lasts.law.events import (
    DelegationConcentrationHalt,
    DelegationConcentrationWarning,
    LawReviewTriggered,
    TransparencyEscalated,
)


def evaluate_delegation_concentration_trigger(
    in_degree_map: dict[str, int],
    policy: SafetyPolicy,
    now: datetime,
) -> list[Event]:
    """
    Evaluate delegation concentration and emit warnings/halts

    This is a critical anti-tyranny reflex. When power becomes too
    concentrated, it automatically emits warnings and halts.

    Args:
        in_degree_map: Actor -> incoming delegation count
        policy: Safety policy with thresholds
        now: Current time

    Returns:
        List of reflex events (warnings, halts, transparency escalation)
    """
    if not in_degree_map:
        return []

    metrics = compute_concentration_metrics(in_degree_map)
    events: list[Event] = []

    # Check HALT thresholds (most severe)
    is_gini_halt = metrics.gini_coefficient >= policy.delegation_gini_halt
    is_degree_halt = metrics.max_in_degree >= policy.delegation_in_degree_halt

    if is_gini_halt or is_degree_halt:
        # Emit halt event
        automatic_responses = []
        reason_parts = []

        if is_gini_halt:
            reason_parts.append(
                f"Gini coefficient {metrics.gini_coefficient:.3f} >= {policy.delegation_gini_halt}"
            )
        if is_degree_halt:
            reason_parts.append(
                f"Max in-degree {metrics.max_in_degree} >= {policy.delegation_in_degree_halt}"
            )

        # Automatic transparency escalation on HALT
        if policy.transparency_escalation_on_halt:
            automatic_responses.append("transparency_escalated")

        halt_event = Event(
            event_id=generate_id(),
            stream_id="system",
            stream_type="feedback",
            version=1,
            command_id=generate_id(),
            event_type="DelegationConcentrationHalt",
            occurred_at=now,
            actor_id="system",
            payload=DelegationConcentrationHalt(
                triggered_at=now,
                gini_coefficient=metrics.gini_coefficient,
                max_in_degree=metrics.max_in_degree,
                halt_threshold_gini=policy.delegation_gini_halt,
                halt_threshold_in_degree=policy.delegation_in_degree_halt,
                automatic_responses=automatic_responses,
                reason="; ".join(reason_parts),
            ).model_dump(mode="json"),
        )
        events.append(halt_event)

        # Emit transparency escalation event
        if policy.transparency_escalation_on_halt:
            transparency_event = Event(
                event_id=generate_id(),
                stream_id="system",
                stream_type="feedback",
                version=2,
                command_id=generate_id(),
                event_type="TransparencyEscalated",
                occurred_at=now,
                actor_id="system",
                payload=TransparencyEscalated(
                    escalated_at=now,
                    scope="global",
                    previous_level="private",
                    new_level="aggregate_plus",
                    trigger_event="DelegationConcentrationHalt",
                    reason="Automatic response to delegation concentration halt",
                ).model_dump(mode="json"),
            )
            events.append(transparency_event)

        return events

    # Check WARNING thresholds (less severe)
    is_gini_warn = metrics.gini_coefficient >= policy.delegation_gini_warn
    is_degree_warn = metrics.max_in_degree >= policy.delegation_in_degree_warn

    if is_gini_warn or is_degree_warn:
        reason_parts = []
        if is_gini_warn:
            reason_parts.append(
                f"Gini coefficient {metrics.gini_coefficient:.3f} >= {policy.delegation_gini_warn}"
            )
        if is_degree_warn:
            reason_parts.append(
                f"Max in-degree {metrics.max_in_degree} >= {policy.delegation_in_degree_warn}"
            )

        warning_event = Event(
            event_id=generate_id(),
            stream_id="system",
            stream_type="feedback",
            version=1,
            command_id=generate_id(),
            event_type="DelegationConcentrationWarning",
            occurred_at=now,
            actor_id="system",
            payload=DelegationConcentrationWarning(
                triggered_at=now,
                gini_coefficient=metrics.gini_coefficient,
                max_in_degree=metrics.max_in_degree,
                warn_threshold_gini=policy.delegation_gini_warn,
                warn_threshold_in_degree=policy.delegation_in_degree_warn,
                reason="; ".join(reason_parts),
            ).model_dump(mode="json"),
        )
        events.append(warning_event)

    return events


def evaluate_law_review_trigger(
    overdue_laws: list[dict],
    now: datetime,
) -> list[Event]:
    """
    Evaluate law review checkpoints and trigger overdue reviews

    This ensures laws don't drift indefinitely without review.

    Args:
        overdue_laws: List of laws with overdue checkpoints
        now: Current time

    Returns:
        List of LawReviewTriggered events
    """
    events: list[Event] = []

    for law in overdue_laws:
        # Only trigger if not already in REVIEW status
        if law.get("status") != "REVIEW":
            review_event = Event(
                event_id=generate_id(),
                stream_id=law["law_id"],
                stream_type="law",
                version=law.get("version", 1) + 1,
                command_id=generate_id(),
                event_type="LawReviewTriggered",
                occurred_at=now,
                actor_id="system",
                payload=LawReviewTriggered(
                    law_id=law["law_id"],
                    triggered_at=now,
                    triggered_by=None,  # System trigger
                    reason="checkpoint_overdue",
                    checkpoint_index=law.get("next_checkpoint_index"),
                ).model_dump(mode="json"),
            )
            events.append(review_event)

    return events


def evaluate_all_triggers(
    in_degree_map: dict[str, int],
    overdue_laws: list[dict],
    policy: SafetyPolicy,
    time_provider: TimeProvider,
) -> list[Event]:
    """
    Evaluate all automatic triggers and return reflex events

    This is the main entry point for the trigger system.
    Called by TickEngine periodically.

    Args:
        in_degree_map: Delegation concentration data
        overdue_laws: Laws with overdue checkpoints
        policy: Safety policy
        time_provider: Time source

    Returns:
        List of all triggered events
    """
    now = time_provider.now()
    events: list[Event] = []

    # Evaluate delegation concentration
    concentration_events = evaluate_delegation_concentration_trigger(
        in_degree_map, policy, now
    )
    events.extend(concentration_events)

    # Evaluate law review checkpoints
    review_events = evaluate_law_review_trigger(overdue_laws, now)
    events.extend(review_events)

    return events
