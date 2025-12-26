"""
Law Module Handlers - Command→Event transformation

Handlers are the decision-making layer. They:
1. Load current state (from projections)
2. Validate invariants
3. Generate events if valid
4. Return events for append to event store

Fun fact: Handlers should be "almost boring" - all the interesting
logic is in invariants (testable) and projections (rebuildable).
Handlers just orchestrate!
"""

from datetime import datetime, timedelta

from freedom_that_lasts.kernel.errors import DelegationNotFound, LawNotFound
from freedom_that_lasts.kernel.events import Event, create_event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    CreateLaw,
    CreateWorkspace,
    DelegateDecisionRight,
    RevokeDelegation,
    TriggerLawReview,
)
from freedom_that_lasts.law.events import (
    DecisionRightDelegated,
    LawActivated,
    LawCreated,
    LawReviewTriggered,
    WorkspaceCreated,
)
from freedom_that_lasts.law.invariants import (
    compute_next_checkpoint,
    validate_acyclic_delegation,
    validate_delegation_ttl,
    validate_law_activation,
)


class LawCommandHandlers:
    """
    Command handlers for the law module

    Handlers convert commands into events, enforcing invariants.
    They depend on projections to get current state.
    """

    def __init__(
        self,
        time_provider: TimeProvider,
        safety_policy: SafetyPolicy,
    ) -> None:
        """
        Initialize handlers with dependencies

        Args:
            time_provider: For timestamps (injectable for testing)
            safety_policy: Constitutional parameters
        """
        self.time_provider = time_provider
        self.safety_policy = safety_policy

    def handle_create_workspace(
        self,
        command: CreateWorkspace,
        command_id: str,
        actor_id: str | None,
    ) -> list[Event]:
        """
        Handle CreateWorkspace command

        Args:
            command: CreateWorkspace command
            command_id: Idempotency key
            actor_id: Who issued the command

        Returns:
            List of events to append
        """
        now = self.time_provider.now()
        workspace_id = generate_id()

        # Create event
        event_payload = WorkspaceCreated(
            workspace_id=workspace_id,
            name=command.name,
            parent_workspace_id=command.parent_workspace_id,
            scope=command.scope,
            created_at=now,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=workspace_id,
            stream_type="workspace",
            event_type="WorkspaceCreated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=1,
        )

        return [event]

    def handle_delegate_decision_right(
        self,
        command: DelegateDecisionRight,
        command_id: str,
        actor_id: str | None,
        workspace_registry: dict,  # From projection
        delegation_edges: list,  # From projection
    ) -> list[Event]:
        """
        Handle DelegateDecisionRight command

        Validates:
        - TTL <= policy maximum
        - Workspace exists
        - No cycle created

        Args:
            command: DelegateDecisionRight command
            command_id: Idempotency key
            actor_id: Who issued the command
            workspace_registry: Current workspaces
            delegation_edges: Current delegation edges

        Returns:
            List of events to append

        Raises:
            TTLExceedsMaximum: If TTL too long
            WorkspaceNotFound: If workspace doesn't exist
            DelegationCycleDetected: If would create cycle
        """
        now = self.time_provider.now()

        # Validate TTL
        validate_delegation_ttl(command.ttl_days, self.safety_policy)

        # Validate workspace exists
        if command.workspace_id not in workspace_registry:
            from freedom_that_lasts.kernel.errors import WorkspaceNotFound

            raise WorkspaceNotFound(command.workspace_id)

        # Validate acyclic graph
        validate_acyclic_delegation(
            delegation_edges,
            command.from_actor,
            command.to_actor,
            now,
        )

        # Generate delegation ID and compute expiry
        delegation_id = generate_id()
        expires_at = now + timedelta(days=command.ttl_days)

        # Use policy default if visibility not specified
        visibility = command.visibility or self.safety_policy.delegation_visibility_default

        # Create event
        event_payload = DecisionRightDelegated(
            delegation_id=delegation_id,
            workspace_id=command.workspace_id,
            from_actor=command.from_actor,
            to_actor=command.to_actor,
            delegated_at=now,
            ttl_days=command.ttl_days,
            expires_at=expires_at,
            renewable=command.renewable,
            visibility=visibility,
            purpose_tag=command.purpose_tag,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=delegation_id,
            stream_type="delegation",
            event_type="DecisionRightDelegated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=1,
        )

        return [event]

    def handle_revoke_delegation(
        self,
        command: RevokeDelegation,
        command_id: str,
        actor_id: str | None,
        delegation_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle RevokeDelegation command

        Args:
            command: RevokeDelegation command
            command_id: Idempotency key
            actor_id: Who issued the command
            delegation_registry: Current delegations

        Returns:
            List of events to append

        Raises:
            DelegationNotFound: If delegation doesn't exist
        """
        now = self.time_provider.now()

        # Validate delegation exists
        if command.delegation_id not in delegation_registry:
            raise DelegationNotFound(command.delegation_id)

        # Get current version from registry
        delegation = delegation_registry[command.delegation_id]
        current_version = delegation.get("version", 1)

        # Create event
        from freedom_that_lasts.law.events import DelegationRevoked

        event_payload = DelegationRevoked(
            delegation_id=command.delegation_id,
            revoked_at=now,
            revoked_by=actor_id or "system",
            reason=command.reason,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.delegation_id,
            stream_type="delegation",
            event_type="DelegationRevoked",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_create_law(
        self,
        command: CreateLaw,
        command_id: str,
        actor_id: str | None,
        workspace_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle CreateLaw command

        Validates:
        - Workspace exists
        - Checkpoint schedule meets minimum requirements

        Args:
            command: CreateLaw command
            command_id: Idempotency key
            actor_id: Who issued the command
            workspace_registry: Current workspaces

        Returns:
            List of events to append

        Raises:
            WorkspaceNotFound: If workspace doesn't exist
            InvalidCheckpointSchedule: If checkpoints don't meet minimums
        """
        now = self.time_provider.now()

        # Validate workspace and checkpoints
        validate_law_activation(
            command.workspace_id,
            command.checkpoints,
            workspace_registry,
            self.safety_policy,
        )

        # Generate law ID
        law_id = generate_id()

        # Create event
        event_payload = LawCreated(
            law_id=law_id,
            workspace_id=command.workspace_id,
            title=command.title,
            scope=command.scope,
            reversibility_class=command.reversibility_class,
            checkpoints=command.checkpoints,
            params=command.params,
            created_at=now,
            created_by=actor_id,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=law_id,
            stream_type="law",
            event_type="LawCreated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=1,
        )

        return [event]

    def handle_activate_law(
        self,
        command: ActivateLaw,
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle ActivateLaw command

        Activates a law, starting the checkpoint clock.

        Args:
            command: ActivateLaw command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Compute first checkpoint
        checkpoints = law["checkpoints"]
        next_checkpoint_at, next_checkpoint_index = compute_next_checkpoint(
            now, checkpoints, 0
        )

        # Create event
        event_payload = LawActivated(
            law_id=command.law_id,
            activated_at=now,
            activated_by=actor_id,
            next_checkpoint_at=next_checkpoint_at,  # type: ignore
            next_checkpoint_index=next_checkpoint_index,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawActivated",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_trigger_law_review(
        self,
        command: TriggerLawReview,
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle TriggerLawReview command

        Args:
            command: TriggerLawReview command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Create event
        event_payload = LawReviewTriggered(
            law_id=command.law_id,
            triggered_at=now,
            triggered_by=actor_id,
            reason=command.reason,
            checkpoint_index=law.get("next_checkpoint_index"),
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawReviewTriggered",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_complete_law_review(
        self,
        command,  # CompleteLawReview
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle CompleteLawReview command

        Completes a review with outcome:
        - continue: Resume ACTIVE, advance to next checkpoint
        - adjust: Move to ADJUST status for modifications
        - sunset: Schedule law for termination

        Args:
            command: CompleteLawReview command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Compute next checkpoint if outcome is "continue"
        next_checkpoint_at = None
        if command.outcome == "continue":
            checkpoints = law["checkpoints"]
            activated_at_str = law.get("activated_at")
            if activated_at_str:
                from datetime import datetime as dt

                activated_at = (
                    dt.fromisoformat(activated_at_str)
                    if isinstance(activated_at_str, str)
                    else activated_at_str
                )
                current_index = law.get("next_checkpoint_index", 0)
                next_index = current_index + 1

                if next_index < len(checkpoints):
                    next_checkpoint_at, _ = compute_next_checkpoint(
                        activated_at, checkpoints, next_index
                    )

        # Create event
        from freedom_that_lasts.law.events import LawReviewCompleted

        event_payload = LawReviewCompleted(
            law_id=command.law_id,
            completed_at=now,
            completed_by=actor_id or "system",
            outcome=command.outcome,
            notes=command.notes,
            next_checkpoint_at=next_checkpoint_at,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawReviewCompleted",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_adjust_law(
        self,
        command,  # AdjustLaw
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle AdjustLaw command

        Modifies a law based on review feedback, then returns to ACTIVE.

        Args:
            command: AdjustLaw command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append (AdjustLaw + LawActivated)

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Create adjustment event
        from freedom_that_lasts.law.events import LawAdjusted

        adjust_payload = LawAdjusted(
            law_id=command.law_id,
            adjusted_at=now,
            adjusted_by=actor_id or "system",
            changes=command.changes,
            reason=command.reason,
        ).model_dump(mode="json")

        adjust_event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawAdjusted",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=adjust_payload,
            version=current_version + 1,
        )

        # After adjustment, reactivate with next checkpoint
        checkpoints = law["checkpoints"]
        activated_at_str = law.get("activated_at")
        if activated_at_str:
            from datetime import datetime as dt

            activated_at = (
                dt.fromisoformat(activated_at_str)
                if isinstance(activated_at_str, str)
                else activated_at_str
            )
            current_index = law.get("next_checkpoint_index", 0)
            next_index = current_index + 1

            next_checkpoint_at, next_checkpoint_index = compute_next_checkpoint(
                activated_at, checkpoints, next_index
            )

            # Reactivate
            from freedom_that_lasts.law.events import LawActivated

            reactivate_payload = LawActivated(
                law_id=command.law_id,
                activated_at=now,
                activated_by=actor_id,
                next_checkpoint_at=next_checkpoint_at,  # type: ignore
                next_checkpoint_index=next_checkpoint_index,
            ).model_dump(mode="json")

            reactivate_event = create_event(
                event_id=generate_id(),
                stream_id=command.law_id,
                stream_type="law",
                event_type="LawActivated",
                occurred_at=now,
                command_id=generate_id(),  # Different command for reactivation
                actor_id=actor_id,
                payload=reactivate_payload,
                version=current_version + 2,
            )

            return [adjust_event, reactivate_event]
        else:
            return [adjust_event]

    def handle_schedule_law_sunset(
        self,
        command,  # ScheduleLawSunset
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle ScheduleLawSunset command

        Schedules a law for termination after specified days.

        Args:
            command: ScheduleLawSunset command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Compute sunset date
        from datetime import timedelta

        sunset_at = now + timedelta(days=command.sunset_days)

        # Create event
        from freedom_that_lasts.law.events import LawSunsetScheduled

        event_payload = LawSunsetScheduled(
            law_id=command.law_id,
            scheduled_at=now,
            sunset_at=sunset_at,
            reason=command.reason,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawSunsetScheduled",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]

    def handle_archive_law(
        self,
        command,  # ArchiveLaw
        command_id: str,
        actor_id: str | None,
        law_registry: dict,  # From projection
    ) -> list[Event]:
        """
        Handle ArchiveLaw command

        Archives a law (final state, preserved for historical record).

        Args:
            command: ArchiveLaw command
            command_id: Idempotency key
            actor_id: Who issued the command
            law_registry: Current laws

        Returns:
            List of events to append

        Raises:
            LawNotFound: If law doesn't exist
        """
        now = self.time_provider.now()

        # Validate law exists
        if command.law_id not in law_registry:
            raise LawNotFound(command.law_id)

        law = law_registry[command.law_id]
        current_version = law.get("version", 1)

        # Create event
        from freedom_that_lasts.law.events import LawArchived

        event_payload = LawArchived(
            law_id=command.law_id,
            archived_at=now,
            reason=command.reason,
        ).model_dump(mode="json")

        event = create_event(
            event_id=generate_id(),
            stream_id=command.law_id,
            stream_type="law",
            event_type="LawArchived",
            occurred_at=now,
            command_id=command_id,
            actor_id=actor_id,
            payload=event_payload,
            version=current_version + 1,
        )

        return [event]
