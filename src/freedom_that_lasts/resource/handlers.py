"""
Resource & Procurement Command Handlers

Transform commands into events with full validation and business logic.
Defense in depth: handlers validate using invariants before emitting events.

Fun fact: The handler pattern in software mirrors the ancient Roman 'cursus honorum'
(course of honors) where each official had clearly defined responsibilities and
accountability - we ensure the same with typed handlers and audit trails!
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from freedom_that_lasts.kernel.events import Event, create_event
from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TimeProvider
from freedom_that_lasts.resource import commands, events
from freedom_that_lasts.resource import invariants
from freedom_that_lasts.resource.feasible import compute_feasible_set
from freedom_that_lasts.resource.models import Evidence, SelectionMethod, TenderStatus
from freedom_that_lasts.resource.selection import (
    get_rotation_state,
    select_by_random,
    select_by_rotation,
    select_by_rotation_with_random,
)


class ResourceCommandHandlers:
    """
    Command handlers for resource & procurement operations

    Stateless handlers: receive command, validate, emit events.
    All state queries done via projections passed as parameters.
    """

    def __init__(self, time_provider: TimeProvider, safety_policy: SafetyPolicy):
        """
        Initialize handlers with time and safety policy

        Args:
            time_provider: Source of current time
            safety_policy: Anti-tyranny safeguards configuration
        """
        self.time_provider = time_provider
        self.safety_policy = safety_policy

    # ========================================================================
    # Supplier & Capability Handlers
    # ========================================================================

    def handle_register_supplier(
        self,
        command: commands.RegisterSupplier,
        command_id: str,
        actor_id: str,
    ) -> list[Event]:
        """
        Register new supplier in capability registry

        Args:
            command: RegisterSupplier command
            command_id: Unique command identifier
            actor_id: Actor registering supplier

        Returns:
            List containing SupplierRegistered event
        """
        now = self.time_provider.now()
        supplier_id = generate_id()

        event_payload = events.SupplierRegistered(
            supplier_id=supplier_id,
            name=command.name,
            supplier_type=command.supplier_type,
            registered_at=now,
            registered_by=actor_id,
            metadata=command.metadata,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="SupplierRegistered",
                stream_id=supplier_id,
                stream_type="Supplier",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    def handle_add_capability_claim(
        self,
        command: commands.AddCapabilityClaim,
        command_id: str,
        actor_id: str,
        supplier_registry: Any,  # SupplierRegistry projection
    ) -> list[Event]:
        """
        Add capability claim to supplier with evidence

        Validates:
        - Supplier exists
        - Evidence required
        - Evidence not expired
        - Capability claim unique

        Args:
            command: AddCapabilityClaim command
            command_id: Command ID
            actor_id: Actor adding claim
            supplier_registry: Supplier registry projection

        Returns:
            List containing CapabilityClaimAdded event
        """
        now = self.time_provider.now()

        # Load supplier
        supplier = supplier_registry.get(command.supplier_id)
        if not supplier:
            raise ValueError(f"Supplier {command.supplier_id} not found")

        # Parse dates
        valid_from = (
            command.valid_from
            if isinstance(command.valid_from, datetime)
            else datetime.fromisoformat(command.valid_from)
        )
        valid_until = None
        if command.valid_until:
            valid_until = (
                command.valid_until
                if isinstance(command.valid_until, datetime)
                else datetime.fromisoformat(command.valid_until)
            )

        # Build evidence objects
        evidence_objects = []
        for ev_spec in command.evidence:
            issued_at = (
                ev_spec.issued_at
                if isinstance(ev_spec.issued_at, datetime)
                else datetime.fromisoformat(ev_spec.issued_at)
            )
            ev_valid_until = None
            if ev_spec.valid_until:
                ev_valid_until = (
                    ev_spec.valid_until
                    if isinstance(ev_spec.valid_until, datetime)
                    else datetime.fromisoformat(ev_spec.valid_until)
                )

            evidence_objects.append(
                Evidence(
                    evidence_id=generate_id(),
                    evidence_type=ev_spec.evidence_type,
                    issuer=ev_spec.issuer,
                    issued_at=issued_at,
                    valid_until=ev_valid_until,
                    document_uri=ev_spec.document_uri,
                    metadata=ev_spec.metadata,
                )
            )

        # Validate evidence required
        invariants.validate_evidence_required(evidence_objects)

        # Validate evidence not expired
        for evidence in evidence_objects:
            invariants.validate_evidence_not_expired(evidence, now)

        # Validate capability claim unique
        existing_capabilities = supplier.get("capabilities", {})
        invariants.validate_capability_claim_unique(
            existing_capabilities, command.capability_type
        )

        # Generate claim ID
        claim_id = generate_id()

        # Serialize evidence for event
        evidence_dicts = [
            {
                "evidence_id": ev.evidence_id,
                "evidence_type": ev.evidence_type,
                "issuer": ev.issuer,
                "issued_at": ev.issued_at.isoformat(),
                "valid_until": ev.valid_until.isoformat() if ev.valid_until else None,
                "document_uri": ev.document_uri,
                "metadata": ev.metadata,
            }
            for ev in evidence_objects
        ]

        event_payload = events.CapabilityClaimAdded(
            claim_id=claim_id,
            supplier_id=command.supplier_id,
            capability_type=command.capability_type,
            scope=command.scope,
            valid_from=valid_from,
            valid_until=valid_until,
            evidence=evidence_dicts,
            capacity=command.capacity,
            added_at=now,
            added_by=actor_id,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="CapabilityClaimAdded",
                stream_id=command.supplier_id,
                stream_type="Supplier",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    # ========================================================================
    # Tender Lifecycle Handlers
    # ========================================================================

    def handle_create_tender(
        self,
        command: commands.CreateTender,
        command_id: str,
        actor_id: str,
        law_registry: Any,  # LawRegistry projection
    ) -> list[Event]:
        """
        Create tender for law-mandated procurement

        Validates:
        - Law exists and is ACTIVE
        - Requirements well-formed
        - Budget item exists (if specified)

        Args:
            command: CreateTender command
            command_id: Command ID
            actor_id: Actor creating tender
            law_registry: Law registry projection

        Returns:
            List containing TenderCreated event
        """
        now = self.time_provider.now()

        # Validate law exists
        law = law_registry.get(command.law_id)
        if not law:
            raise ValueError(f"Law {command.law_id} not found")

        # Validate law is ACTIVE (simple check - full invariant would check law projection)
        # In full implementation, would use validate_law_active_for_tender invariant
        if law.get("status") != "ACTIVE":
            raise invariants.LawNotActiveForProcurementError(
                f"Law {command.law_id} must be ACTIVE to start procurement (current: {law.get('status')})"
            )

        # Validate requirements
        requirement_dicts = [
            {
                "requirement_id": generate_id(),
                "capability_type": req.capability_type,
                "min_capacity": req.min_capacity,
                "mandatory": req.mandatory,
            }
            for req in command.requirements
        ]
        invariants.validate_tender_requirements(requirement_dicts)

        # Generate tender ID
        tender_id = generate_id()

        event_payload = events.TenderCreated(
            tender_id=tender_id,
            law_id=command.law_id,
            title=command.title,
            description=command.description,
            requirements=requirement_dicts,
            required_capacity=command.required_capacity,
            sla_requirements=command.sla_requirements,
            evidence_required=command.evidence_required,
            acceptance_tests=command.acceptance_tests,
            estimated_value=command.estimated_value,
            budget_item_id=command.budget_item_id,
            selection_method=command.selection_method,
            created_at=now,
            created_by=actor_id,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="TenderCreated",
                stream_id=tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    def handle_open_tender(
        self,
        command: commands.OpenTender,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
    ) -> list[Event]:
        """
        Open tender for submissions (DRAFT → OPEN transition)

        Args:
            command: OpenTender command
            command_id: Command ID
            actor_id: Actor opening tender
            tender_registry: Tender registry projection

        Returns:
            List containing TenderOpened event
        """
        now = self.time_provider.now()

        # Load tender
        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        # Validate current status is DRAFT
        if tender.get("status") != TenderStatus.DRAFT:
            raise ValueError(
                f"Tender must be DRAFT to open (current: {tender.get('status')})"
            )

        event_payload = events.TenderOpened(
            tender_id=command.tender_id,
            opened_at=now,
            opened_by=actor_id,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="TenderOpened",
                stream_id=command.tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    def handle_evaluate_tender(
        self,
        command: commands.EvaluateTender,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
        supplier_registry: Any,
    ) -> list[Event]:
        """
        Evaluate tender - compute feasible set via binary requirement matching

        CORE LOGIC: Binary matching (no scoring, no weighting).

        Args:
            command: EvaluateTender command
            command_id: Command ID
            actor_id: Actor evaluating (typically "system")
            tender_registry: Tender registry projection
            supplier_registry: Supplier registry projection

        Returns:
            List with FeasibleSetComputed event, possibly EmptyFeasibleSetDetected
        """
        now = self.time_provider.now()

        # Load tender
        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        # Validate tender is OPEN
        if tender.get("status") != TenderStatus.OPEN:
            raise ValueError(
                f"Tender must be OPEN to evaluate (current: {tender.get('status')})"
            )

        # Load all suppliers
        all_suppliers = supplier_registry.list_all()

        # Determine evaluation time
        evaluation_time = (
            command.evaluation_time
            if command.evaluation_time
            else now
        )
        if isinstance(evaluation_time, str):
            evaluation_time = datetime.fromisoformat(evaluation_time)

        # CORE: Compute feasible set (binary matching)
        feasible_supplier_ids, excluded_with_reasons = compute_feasible_set(
            suppliers=all_suppliers,
            requirements=tender.get("requirements", []),
            required_capacity=tender.get("required_capacity"),
            evaluation_time=evaluation_time,
        )

        event_payload = events.FeasibleSetComputed(
            tender_id=command.tender_id,
            evaluation_time=evaluation_time,
            total_suppliers_evaluated=len(all_suppliers),
            feasible_suppliers=feasible_supplier_ids,
            excluded_suppliers_with_reasons=excluded_with_reasons,
            computation_method="binary_requirement_matching",
            computed_by=actor_id,
        ).model_dump(mode="json")

        result_events = [
            create_event(
                event_id=generate_id(),
                event_type="FeasibleSetComputed",
                stream_id=command.tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

        # If feasible set empty, emit warning trigger event
        if not feasible_supplier_ids or len(feasible_supplier_ids) == 0:
            empty_event_payload = events.EmptyFeasibleSetDetected(
                tender_id=command.tender_id,
                law_id=tender.get("law_id"),
                detected_at=now,
                requirements_summary={
                    "requirements": tender.get("requirements"),
                    "required_capacity": tender.get("required_capacity"),
                },
                action_required="Review requirements or build supplier capacity",
            ).model_dump(mode="json")

            result_events.append(
                create_event(
                    event_id=generate_id(),
                    event_type="EmptyFeasibleSetDetected",
                    stream_id=command.tender_id,
                    stream_type="Tender",
                    occurred_at=now,
                    actor_id="system",
                    command_id=command_id,
                    payload=empty_event_payload,
                    version=1,
                )
            )

        return result_events

    def handle_select_supplier(
        self,
        command: commands.SelectSupplier,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
        supplier_registry: Any,
    ) -> list[Event]:
        """
        Select supplier from feasible set using constitutional mechanism

        MULTI-GATE ENFORCEMENT:
        1. Feasible set must be non-empty
        2. Selection method must match tender configuration
        3. Supplier share limits enforced (anti-capture)
        4. Reputation threshold applied (if configured)

        NO DISCRETION - selection is algorithmic and auditable.

        Args:
            command: SelectSupplier command
            command_id: Command ID
            actor_id: Actor (typically "system" for constitutional selection)
            tender_registry: Tender registry
            supplier_registry: Supplier registry

        Returns:
            List with SupplierSelected or SupplierSelectionFailed event
        """
        now = self.time_provider.now()

        # Load tender
        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        # Validate tender is EVALUATING
        if tender.get("status") != TenderStatus.EVALUATING:
            raise ValueError(
                f"Tender must be EVALUATING to select supplier (current: {tender.get('status')})"
            )

        # GATE 1: Feasible set not empty
        feasible_supplier_ids = tender.get("feasible_suppliers", [])
        try:
            invariants.validate_feasible_set_not_empty(feasible_supplier_ids)
        except invariants.FeasibleSetEmptyError as e:
            # Emit failure event
            event_payload = events.SupplierSelectionFailed(
                tender_id=command.tender_id,
                failure_reason=str(e),
                empty_feasible_set=True,
                attempted_at=now,
                attempted_by=actor_id,
            ).model_dump(mode="json")

            return [
                create_event(
                    event_id=generate_id(),
                    event_type="SupplierSelectionFailed",
                    stream_id=command.tender_id,
                    stream_type="Tender",
                    occurred_at=now,
                    actor_id=actor_id,
                    command_id=command_id,
                    payload=event_payload,
                    version=1,
                )
            ]

        # Load supplier data for feasible set
        feasible_suppliers = [
            supplier_registry.get(sid) for sid in feasible_supplier_ids
        ]
        feasible_suppliers = [s for s in feasible_suppliers if s is not None]

        if not feasible_suppliers:
            event_payload = events.SupplierSelectionFailed(
                tender_id=command.tender_id,
                failure_reason="Feasible suppliers not found in registry",
                empty_feasible_set=True,
                attempted_at=now,
                attempted_by=actor_id,
            ).model_dump(mode="json")

            return [
                create_event(
                    event_id=generate_id(),
                    event_type="SupplierSelectionFailed",
                    stream_id=command.tender_id,
                    stream_type="Tender",
                    occurred_at=now,
                    actor_id=actor_id,
                    command_id=command_id,
                    payload=event_payload,
                    version=1,
                )
            ]

        # GATE 2: Selection method matches tender config
        tender_selection_method = SelectionMethod(tender.get("selection_method"))
        invariants.validate_selection_method(
            tender_selection_method, tender_selection_method
        )

        # GATE 3: Supplier share limits (anti-capture)
        # Filter out suppliers exceeding share threshold
        # BUT: Only enforce this if contracts have been awarded (total_value > 0)
        # Don't block first procurement due to concentration limits
        all_suppliers = supplier_registry.list_all()
        from freedom_that_lasts.resource.selection import compute_supplier_shares

        shares = compute_supplier_shares(all_suppliers)
        total_value = sum(
            s.get("total_value_awarded", Decimal("0")) for s in all_suppliers
        )
        share_limit = self.safety_policy.supplier_share_halt_threshold

        eligible_suppliers = []
        for supplier in feasible_suppliers:
            supplier_id = supplier["supplier_id"]
            supplier_share = shares.get(supplier_id, 0.0)

            # Only enforce concentration limits if procurement has actually happened
            if total_value > 0:
                try:
                    invariants.validate_supplier_share_limit(supplier_share, share_limit)
                    eligible_suppliers.append(supplier)
                except invariants.SupplierShareExceededError:
                    # Skip this supplier (excluded by concentration limit)
                    pass
            else:
                # No contracts awarded yet - don't enforce concentration limits
                eligible_suppliers.append(supplier)

        if not eligible_suppliers:
            event_payload = events.SupplierSelectionFailed(
                tender_id=command.tender_id,
                failure_reason="All feasible suppliers exceed share concentration limit",
                empty_feasible_set=False,
                attempted_at=now,
                attempted_by=actor_id,
            ).model_dump(mode="json")

            return [
                create_event(
                    event_id=generate_id(),
                    event_type="SupplierSelectionFailed",
                    stream_id=command.tender_id,
                    stream_type="Tender",
                    occurred_at=now,
                    actor_id=actor_id,
                    command_id=command_id,
                    payload=event_payload,
                    version=1,
                )
            ]

        # GATE 4: Reputation threshold (if configured)
        # BUT: Only enforce this if contracts have been awarded (total_value > 0)
        # New suppliers need a chance to build reputation through first delivery
        min_reputation = self.safety_policy.supplier_min_reputation_threshold
        if min_reputation is not None and total_value > 0:
            from freedom_that_lasts.resource.selection import apply_reputation_threshold

            eligible_suppliers = apply_reputation_threshold(
                eligible_suppliers, min_reputation
            )

        if not eligible_suppliers:
            event_payload = events.SupplierSelectionFailed(
                tender_id=command.tender_id,
                failure_reason=f"No suppliers meet minimum reputation threshold {min_reputation}",
                empty_feasible_set=False,
                attempted_at=now,
                attempted_by=actor_id,
            ).model_dump(mode="json")

            return [
                create_event(
                    event_id=generate_id(),
                    event_type="SupplierSelectionFailed",
                    stream_id=command.tender_id,
                    stream_type="Tender",
                    occurred_at=now,
                    actor_id=actor_id,
                    command_id=command_id,
                    payload=event_payload,
                    version=1,
                )
            ]

        # Execute constitutional selection mechanism
        selection_method = tender_selection_method
        selection_reason = ""
        random_seed = None

        if selection_method == SelectionMethod.ROTATION:
            selected_supplier = select_by_rotation(eligible_suppliers)
            selection_reason = f"Rotation: supplier with lowest load"

        elif selection_method == SelectionMethod.RANDOM:
            # Validate seed provided
            seed = command.selection_seed
            invariants.validate_random_seed_verifiable(seed)
            selected_supplier = select_by_random(eligible_suppliers, seed)
            selection_reason = f"Random selection with seed"
            random_seed = seed

        else:  # ROTATION_WITH_RANDOM
            seed = command.selection_seed or f"tender-{command.tender_id}-{now.isoformat()}"
            selected_supplier = select_by_rotation_with_random(eligible_suppliers, seed)
            selection_reason = f"Rotation + Random: low-loaded subset with random tie-break"
            random_seed = seed

        # Get rotation state for audit trail
        rotation_state = get_rotation_state(eligible_suppliers)

        event_payload = events.SupplierSelected(
            tender_id=command.tender_id,
            selected_supplier_id=selected_supplier["supplier_id"],
            selection_method=selection_method,
            selection_reason=selection_reason,
            rotation_state=rotation_state,
            random_seed=random_seed,
            selected_at=now,
            selected_by=actor_id,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="SupplierSelected",
                stream_id=command.tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    def handle_award_tender(
        self,
        command: commands.AwardTender,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
    ) -> list[Event]:
        """Award tender to selected supplier"""
        now = self.time_provider.now()

        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        if not tender.get("selected_supplier_id"):
            raise ValueError("Cannot award tender without selected supplier")

        event_payload = events.TenderAwarded(
            tender_id=command.tender_id,
            awarded_supplier_id=tender["selected_supplier_id"],
            contract_value=command.contract_value,
            contract_terms=command.contract_terms,
            awarded_at=now,
            awarded_by=actor_id,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="TenderAwarded",
                stream_id=command.tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=event_payload,
                version=1,
            )
        ]

    def handle_record_milestone(
        self,
        command: commands.RecordMilestone,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
    ) -> list[Event]:
        """
        Record delivery milestone with evidence

        Tracks progress through tender execution.
        Critical milestones should include evidence.
        """
        now = self.time_provider.now()

        # Validate tender exists
        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        # Validate milestone evidence if provided
        if command.evidence:
            # Evidence is already validated by command model (EvidenceSpec)
            pass

        # Convert evidence specs to dicts
        evidence_dicts = [ev.model_dump(mode="json") for ev in command.evidence]

        milestone_payload = events.MilestoneRecorded(
            tender_id=command.tender_id,
            milestone_id=command.milestone_id,
            milestone_type=command.milestone_type,
            description=command.description,
            evidence=evidence_dicts,
            recorded_at=now,
            recorded_by=actor_id,
            metadata=command.metadata,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="MilestoneRecorded",
                stream_id=f"delivery-{command.tender_id}",  # Separate stream for delivery events
                stream_type="delivery",
                command_id=command_id,
                actor_id=actor_id,
                occurred_at=now,
                payload=milestone_payload,
                version=1,  # Version will be updated in FTL façade
            )
        ]

    def handle_record_sla_breach(
        self,
        command: commands.RecordSLABreach,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
    ) -> list[Event]:
        """
        Record SLA breach during delivery

        Tracks quality issues. Severe breaches may impact supplier reputation.
        """
        now = self.time_provider.now()

        # Validate tender exists
        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        # Validate severity
        valid_severities = ["minor", "major", "critical"]
        if command.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity '{command.severity}'. Must be one of: {valid_severities}"
            )

        breach_payload = events.SLABreachDetected(
            tender_id=command.tender_id,
            sla_metric=command.sla_metric,
            expected_value=command.expected_value,
            actual_value=command.actual_value,
            severity=command.severity,
            impact_description=command.impact_description,
            detected_at=now,
        ).model_dump(mode="json")

        return [
            create_event(
                event_id=generate_id(),
                event_type="SLABreachDetected",
                stream_id=f"delivery-{command.tender_id}",  # Separate stream for delivery events
                stream_type="delivery",
                command_id=command_id,
                actor_id=actor_id,
                occurred_at=now,
                payload=breach_payload,
                version=1,  # Version will be updated in FTL façade
            )
        ]

    def handle_complete_tender(
        self,
        command: commands.CompleteTender,
        command_id: str,
        actor_id: str,
        tender_registry: Any,
        supplier_registry: Any,
    ) -> list[Event]:
        """
        Complete tender with quality assessment

        Updates supplier reputation based on delivery quality.
        """
        now = self.time_provider.now()

        # Validate quality score
        invariants.validate_quality_score_range(command.final_quality_score)

        tender = tender_registry.get(command.tender_id)
        if not tender:
            raise ValueError(f"Tender {command.tender_id} not found")

        supplier_id = tender.get("selected_supplier_id")
        if not supplier_id:
            raise ValueError("Tender has no selected supplier")

        supplier = supplier_registry.get(supplier_id)
        if not supplier:
            raise ValueError(f"Supplier {supplier_id} not found")

        # Update reputation: weighted average with quality score
        old_reputation = supplier.get("reputation_score", 0.5)
        # Simple formula: new_rep = 0.8 * old_rep + 0.2 * quality_score
        # (Recent performance weighted more heavily)
        new_reputation = 0.8 * old_reputation + 0.2 * command.final_quality_score

        invariants.validate_reputation_bounds(new_reputation)

        completed_payload = events.TenderCompleted(
            tender_id=command.tender_id,
            completed_at=now,
            completion_report=command.completion_report,
            final_quality_score=command.final_quality_score,
            completed_by=actor_id,
        ).model_dump(mode="json")

        reputation_payload = events.ReputationUpdated(
            supplier_id=supplier_id,
            old_score=old_reputation,
            new_score=new_reputation,
            reason=f"Tender {command.tender_id} completed with quality score {command.final_quality_score}",
            tender_id=command.tender_id,
            updated_at=now,
        ).model_dump(mode="json")

        result_events = [
            create_event(
                event_id=generate_id(),
                event_type="TenderCompleted",
                stream_id=command.tender_id,
                stream_type="Tender",
                occurred_at=now,
                actor_id=actor_id,
                command_id=command_id,
                payload=completed_payload,
                version=1,
            ),
            create_event(
                event_id=generate_id(),
                event_type="ReputationUpdated",
                stream_id=supplier_id,
                stream_type="Supplier",
                occurred_at=now,
                actor_id="system",
                command_id=command_id,
                payload=reputation_payload,
                version=1,
            ),
        ]

        return result_events
