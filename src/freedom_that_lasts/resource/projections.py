"""
Resource & Procurement Projections

Event-sourced read models rebuilt from events.
Projections are the "present" computed from the "history" (event log).

Fun fact: This architecture mirrors how archaeologists reconstruct ancient civilizations
from artifacts (events) - we reconstruct procurement state from immutable event logs!
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.resource.models import TenderStatus


class SupplierRegistry:
    """
    Supplier registry projection

    Tracks all suppliers with their capabilities, reputation, and contract values.
    Rebuilt from SupplierRegistered, CapabilityClaimAdded, ReputationUpdated, TenderAwarded events.
    """

    def __init__(self):
        """Initialize empty supplier registry"""
        self.suppliers: dict[str, dict[str, Any]] = {}

    def apply_event(self, event: Event) -> None:
        """
        Apply event to update projection

        Args:
            event: Event to apply
        """
        if event.event_type == "SupplierRegistered":
            self._apply_supplier_registered(event)
        elif event.event_type == "CapabilityClaimAdded":
            self._apply_capability_claim_added(event)
        elif event.event_type == "CapabilityClaimUpdated":
            self._apply_capability_claim_updated(event)
        elif event.event_type == "CapabilityClaimRevoked":
            self._apply_capability_claim_revoked(event)
        elif event.event_type == "ReputationUpdated":
            self._apply_reputation_updated(event)
        elif event.event_type == "TenderAwarded":
            self._apply_tender_awarded(event)

    def _apply_supplier_registered(self, event: Event) -> None:
        """Create supplier entry"""
        payload = event.payload
        self.suppliers[payload["supplier_id"]] = {
            "supplier_id": payload["supplier_id"],
            "name": payload["name"],
            "supplier_type": payload["supplier_type"],
            "capabilities": {},
            "reputation_score": 0.5,  # Default for new suppliers
            "total_value_awarded": Decimal("0"),
            "created_at": payload["registered_at"],
            "metadata": payload.get("metadata", {}),
            "version": event.version,
        }

    def _apply_capability_claim_added(self, event: Event) -> None:
        """Add capability claim to supplier"""
        payload = event.payload
        supplier_id = payload["supplier_id"]

        if supplier_id not in self.suppliers:
            # Shouldn't happen, but defensive
            return

        capability_type = payload["capability_type"]
        self.suppliers[supplier_id]["capabilities"][capability_type] = {
            "claim_id": payload["claim_id"],
            "capability_type": capability_type,
            "scope": payload["scope"],
            "valid_from": payload["valid_from"],
            "valid_until": payload.get("valid_until"),
            "evidence": payload["evidence"],
            "capacity": payload.get("capacity"),
            "verified": True,  # Auto-verified for now (in prod would have verification flow)
            "added_at": payload["added_at"],
        }
        self.suppliers[supplier_id]["version"] = event.version

    def _apply_capability_claim_updated(self, event: Event) -> None:
        """Update existing capability claim"""
        payload = event.payload
        supplier_id = payload["supplier_id"]
        claim_id = payload["claim_id"]

        if supplier_id not in self.suppliers:
            return

        # Find claim by claim_id
        for cap_type, claim in self.suppliers[supplier_id]["capabilities"].items():
            if claim.get("claim_id") == claim_id:
                if payload.get("updated_evidence"):
                    claim["evidence"] = payload["updated_evidence"]
                if payload.get("updated_validity"):
                    claim["valid_until"] = payload["updated_validity"]
                if payload.get("updated_capacity"):
                    claim["capacity"] = payload["updated_capacity"]
                claim["updated_at"] = payload["updated_at"]
                break
        self.suppliers[supplier_id]["version"] = event.version

    def _apply_capability_claim_revoked(self, event: Event) -> None:
        """Remove revoked capability claim"""
        payload = event.payload
        supplier_id = payload["supplier_id"]
        capability_type = payload["capability_type"]

        if supplier_id in self.suppliers:
            self.suppliers[supplier_id]["capabilities"].pop(capability_type, None)
            self.suppliers[supplier_id]["version"] = event.version

    def _apply_reputation_updated(self, event: Event) -> None:
        """Update supplier reputation"""
        payload = event.payload
        supplier_id = payload["supplier_id"]

        if supplier_id in self.suppliers:
            self.suppliers[supplier_id]["reputation_score"] = payload["new_score"]
            self.suppliers[supplier_id]["version"] = event.version

    def _apply_tender_awarded(self, event: Event) -> None:
        """Increment supplier's total_value_awarded"""
        payload = event.payload
        supplier_id = payload["awarded_supplier_id"]

        if supplier_id in self.suppliers:
            current_value = self.suppliers[supplier_id].get(
                "total_value_awarded", Decimal("0")
            )
            # Convert contract_value to Decimal (may be string from JSON serialization)
            contract_value = payload["contract_value"]
            if isinstance(contract_value, str):
                contract_value = Decimal(contract_value)
            self.suppliers[supplier_id]["total_value_awarded"] = (
                current_value + contract_value
            )
            # Don't update version - TenderAwarded belongs to tender stream, not supplier stream

    def get(self, supplier_id: str) -> dict[str, Any] | None:
        """Get supplier by ID"""
        return self.suppliers.get(supplier_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all suppliers"""
        return list(self.suppliers.values())

    def list_by_capability(self, capability_type: str) -> list[dict[str, Any]]:
        """List suppliers with specific capability"""
        return [
            s
            for s in self.suppliers.values()
            if capability_type in s.get("capabilities", {})
        ]

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary for serialization"""
        return {"suppliers": self.suppliers}


class TenderRegistry:
    """
    Tender registry projection

    Tracks all tenders with their status, feasible sets, and selections.
    Rebuilt from tender lifecycle events.
    """

    def __init__(self):
        """Initialize empty tender registry"""
        self.tenders: dict[str, dict[str, Any]] = {}

    def apply_event(self, event: Event) -> None:
        """Apply event to update projection"""
        if event.event_type == "TenderCreated":
            self._apply_tender_created(event)
        elif event.event_type == "TenderOpened":
            self._apply_tender_opened(event)
        elif event.event_type == "FeasibleSetComputed":
            self._apply_feasible_set_computed(event)
        elif event.event_type == "SupplierSelected":
            self._apply_supplier_selected(event)
        elif event.event_type == "TenderAwarded":
            self._apply_tender_awarded(event)
        elif event.event_type == "TenderCompleted":
            self._apply_tender_completed(event)
        elif event.event_type == "TenderCancelled":
            self._apply_tender_cancelled(event)

    def _apply_tender_created(self, event: Event) -> None:
        """Create tender in DRAFT status"""
        payload = event.payload
        self.tenders[payload["tender_id"]] = {
            "tender_id": payload["tender_id"],
            "law_id": payload["law_id"],
            "title": payload["title"],
            "description": payload["description"],
            "requirements": payload["requirements"],
            "required_capacity": payload.get("required_capacity"),
            "sla_requirements": payload.get("sla_requirements"),
            "evidence_required": payload.get("evidence_required", []),
            "acceptance_tests": payload.get("acceptance_tests", []),
            "estimated_value": payload.get("estimated_value"),
            "budget_item_id": payload.get("budget_item_id"),
            "selection_method": payload["selection_method"],
            "status": TenderStatus.DRAFT,
            "feasible_suppliers": [],
            "selected_supplier_id": None,
            "selection_reason": None,
            "created_at": payload["created_at"],
            "opened_at": None,
            "awarded_at": None,
            "completed_at": None,
            "version": event.version,
        }

    def _apply_tender_opened(self, event: Event) -> None:
        """Set status to OPEN"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["status"] = TenderStatus.OPEN
            self.tenders[tender_id]["opened_at"] = payload["opened_at"]
            self.tenders[tender_id]["version"] = event.version

    def _apply_feasible_set_computed(self, event: Event) -> None:
        """Store feasible set and set status to EVALUATING"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["status"] = TenderStatus.EVALUATING
            self.tenders[tender_id]["feasible_suppliers"] = payload[
                "feasible_suppliers"
            ]
            self.tenders[tender_id]["evaluation_time"] = payload["evaluation_time"]
            self.tenders[tender_id]["excluded_suppliers_with_reasons"] = payload.get(
                "excluded_suppliers_with_reasons", []
            )
            self.tenders[tender_id]["version"] = event.version

    def _apply_supplier_selected(self, event: Event) -> None:
        """Store selected supplier"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["selected_supplier_id"] = payload[
                "selected_supplier_id"
            ]
            self.tenders[tender_id]["selection_reason"] = payload["selection_reason"]
            self.tenders[tender_id]["selected_at"] = payload["selected_at"]
            self.tenders[tender_id]["version"] = event.version
            # Status remains EVALUATING until awarded

    def _apply_tender_awarded(self, event: Event) -> None:
        """Set status to AWARDED and store contract details"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["status"] = TenderStatus.AWARDED
            self.tenders[tender_id]["contract_value"] = payload["contract_value"]
            self.tenders[tender_id]["contract_terms"] = payload["contract_terms"]
            self.tenders[tender_id]["awarded_at"] = payload["awarded_at"]
            self.tenders[tender_id]["version"] = event.version

    def _apply_tender_completed(self, event: Event) -> None:
        """Set status to COMPLETED"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["status"] = TenderStatus.COMPLETED
            self.tenders[tender_id]["completed_at"] = payload["completed_at"]
            self.tenders[tender_id]["completion_report"] = payload["completion_report"]
            self.tenders[tender_id]["final_quality_score"] = payload[
                "final_quality_score"
            ]
            self.tenders[tender_id]["version"] = event.version

    def _apply_tender_cancelled(self, event: Event) -> None:
        """Set status to CANCELLED"""
        payload = event.payload
        tender_id = payload["tender_id"]

        if tender_id in self.tenders:
            self.tenders[tender_id]["status"] = TenderStatus.CANCELLED
            self.tenders[tender_id]["cancelled_at"] = payload["cancelled_at"]
            self.tenders[tender_id]["cancellation_reason"] = payload["reason"]
            self.tenders[tender_id]["version"] = event.version

    def get(self, tender_id: str) -> dict[str, Any] | None:
        """Get tender by ID"""
        return self.tenders.get(tender_id)

    def list_by_law(self, law_id: str) -> list[dict[str, Any]]:
        """List tenders for specific law"""
        return [t for t in self.tenders.values() if t.get("law_id") == law_id]

    def list_by_status(self, status: TenderStatus | str) -> list[dict[str, Any]]:
        """List tenders with specific status"""
        status_str = status.value if isinstance(status, TenderStatus) else status
        return [t for t in self.tenders.values() if t.get("status") == status_str]

    def list_active(self) -> list[dict[str, Any]]:
        """List active tenders (OPEN, EVALUATING, AWARDED, IN_DELIVERY)"""
        active_statuses = {
            TenderStatus.OPEN,
            TenderStatus.EVALUATING,
            TenderStatus.AWARDED,
            TenderStatus.IN_DELIVERY,
        }
        return [t for t in self.tenders.values() if t.get("status") in active_statuses]

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary"""
        return {"tenders": self.tenders}


class DeliveryLog:
    """
    Delivery log projection

    Tracks delivery milestones, SLA breaches, and completions.
    Used for supplier performance tracking and law checkpoint feedback.
    """

    def __init__(self):
        """Initialize empty delivery log"""
        self.milestones: list[dict[str, Any]] = []
        self.sla_breaches: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def apply_event(self, event: Event) -> None:
        """Apply event to update log"""
        if event.event_type == "MilestoneRecorded":
            self._apply_milestone_recorded(event)
        elif event.event_type == "SLABreachDetected":
            self._apply_sla_breach_detected(event)
        elif event.event_type == "TenderCompleted":
            self._apply_tender_completed(event)

    def _apply_milestone_recorded(self, event: Event) -> None:
        """Append milestone"""
        payload = event.payload
        self.milestones.append({
            "tender_id": payload["tender_id"],
            "milestone_id": payload["milestone_id"],
            "milestone_type": payload["milestone_type"],
            "description": payload["description"],
            "evidence": payload.get("evidence", []),
            "recorded_at": payload["recorded_at"],
            "metadata": payload.get("metadata", {}),
        })

    def _apply_sla_breach_detected(self, event: Event) -> None:
        """Append SLA breach"""
        payload = event.payload
        self.sla_breaches.append({
            "tender_id": payload["tender_id"],
            "sla_metric": payload["sla_metric"],
            "expected_value": payload["expected_value"],
            "actual_value": payload["actual_value"],
            "severity": payload["severity"],
            "impact_description": payload["impact_description"],
            "detected_at": payload["detected_at"],
        })

    def _apply_tender_completed(self, event: Event) -> None:
        """Append completion"""
        payload = event.payload
        self.completions.append({
            "tender_id": payload["tender_id"],
            "completed_at": payload["completed_at"],
            "completion_report": payload["completion_report"],
            "final_quality_score": payload["final_quality_score"],
        })

    def get_by_tender(self, tender_id: str) -> dict[str, Any]:
        """Get all logs for specific tender"""
        return {
            "milestones": [m for m in self.milestones if m["tender_id"] == tender_id],
            "sla_breaches": [
                b for b in self.sla_breaches if b["tender_id"] == tender_id
            ],
            "completions": [c for c in self.completions if c["tender_id"] == tender_id],
        }

    def get_milestones(self, tender_id: str) -> list[dict[str, Any]]:
        """Get milestones for tender"""
        return [m for m in self.milestones if m["tender_id"] == tender_id]

    def get_sla_breaches(self, tender_id: str) -> list[dict[str, Any]]:
        """Get SLA breaches for tender"""
        return [b for b in self.sla_breaches if b["tender_id"] == tender_id]


class ProcurementHealthProjection:
    """
    Procurement health projection

    Tracks empty feasible sets and supplier concentration warnings/halts.
    Used for anti-capture monitoring and law review triggers.
    """

    def __init__(self):
        """Initialize empty health projection"""
        self.empty_feasible_sets: list[dict[str, Any]] = []
        self.concentration_warnings: list[dict[str, Any]] = []
        self.concentration_halts: list[dict[str, Any]] = []

    def apply_event(self, event: Event) -> None:
        """Apply event to update projection"""
        if event.event_type == "EmptyFeasibleSetDetected":
            self._apply_empty_feasible_set_detected(event)
        elif event.event_type == "SupplierConcentrationWarning":
            self._apply_concentration_warning(event)
        elif event.event_type == "SupplierConcentrationHalt":
            self._apply_concentration_halt(event)

    def _apply_empty_feasible_set_detected(self, event: Event) -> None:
        """Track empty feasible set"""
        payload = event.payload
        self.empty_feasible_sets.append({
            "tender_id": payload["tender_id"],
            "law_id": payload["law_id"],
            "detected_at": payload["detected_at"],
            "requirements_summary": payload["requirements_summary"],
            "action_required": payload.get("action_required"),
        })

    def _apply_concentration_warning(self, event: Event) -> None:
        """Track concentration warning"""
        payload = event.payload
        self.concentration_warnings.append({
            "detected_at": payload["detected_at"],
            "total_procurement_value": payload["total_procurement_value"],
            "supplier_shares": payload["supplier_shares"],
            "gini_coefficient": payload["gini_coefficient"],
            "top_supplier_id": payload["top_supplier_id"],
            "top_supplier_share": payload["top_supplier_share"],
            "threshold_exceeded": payload["threshold_exceeded"],
        })

    def _apply_concentration_halt(self, event: Event) -> None:
        """Track concentration halt"""
        payload = event.payload
        self.concentration_halts.append({
            "detected_at": payload["detected_at"],
            "total_procurement_value": payload["total_procurement_value"],
            "supplier_shares": payload["supplier_shares"],
            "gini_coefficient": payload["gini_coefficient"],
            "halted_supplier_id": payload["halted_supplier_id"],
            "supplier_share": payload["supplier_share"],
            "critical_threshold_exceeded": payload["critical_threshold_exceeded"],
        })

    def has_issues(self, tender_id: str | None = None) -> bool:
        """Check if there are any health issues"""
        if tender_id:
            return any(
                fs["tender_id"] == tender_id for fs in self.empty_feasible_sets
            )
        return (
            len(self.empty_feasible_sets) > 0
            or len(self.concentration_warnings) > 0
            or len(self.concentration_halts) > 0
        )

    def get_latest_concentration_warning(self) -> dict[str, Any] | None:
        """Get most recent concentration warning"""
        if not self.concentration_warnings:
            return None
        return max(self.concentration_warnings, key=lambda w: w["detected_at"])

    def get_latest_concentration_halt(self) -> dict[str, Any] | None:
        """Get most recent concentration halt"""
        if not self.concentration_halts:
            return None
        return max(self.concentration_halts, key=lambda h: h["detected_at"])
