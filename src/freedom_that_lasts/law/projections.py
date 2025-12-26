"""
Law Module Projections - Read models built from events

Projections are denormalized views optimized for queries.
They are rebuilt from the event log, making them disposable and rebuildable.

Fun fact: Projections are like "materialized views" in traditional databases,
but better - they're versioned, rebuildable, and can be customized per use case!
"""

from datetime import datetime
from typing import Any

from freedom_that_lasts.kernel.events import Event
from freedom_that_lasts.law.models import Delegation, DelegationEdge, Law, LawStatus, Workspace


class WorkspaceRegistry:
    """
    Projection: Registry of all workspaces

    Maintains current state of all workspaces for fast lookup.
    """

    def __init__(self) -> None:
        self.workspaces: dict[str, dict[str, Any]] = {}

    def apply_event(self, event: Event) -> None:
        """Apply an event to update projection state"""
        if event.event_type == "WorkspaceCreated":
            self.workspaces[event.payload["workspace_id"]] = {
                "workspace_id": event.payload["workspace_id"],
                "name": event.payload["name"],
                "parent_workspace_id": event.payload.get("parent_workspace_id"),
                "scope": event.payload.get("scope", {}),
                "created_at": event.payload["created_at"],
                "is_active": True,
                "version": event.version,
            }

        elif event.event_type == "WorkspaceArchived":
            workspace_id = event.payload["workspace_id"]
            if workspace_id in self.workspaces:
                self.workspaces[workspace_id]["is_active"] = False
                self.workspaces[workspace_id]["archived_at"] = event.payload["archived_at"]

    def get(self, workspace_id: str) -> dict[str, Any] | None:
        """Get workspace by ID"""
        return self.workspaces.get(workspace_id)

    def list_active(self) -> list[dict[str, Any]]:
        """List all active workspaces"""
        return [ws for ws in self.workspaces.values() if ws["is_active"]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {"workspaces": self.workspaces}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceRegistry":
        """Deserialize from dict"""
        registry = cls()
        registry.workspaces = data.get("workspaces", {})
        return registry


class DelegationGraph:
    """
    Projection: Delegation graph for cycle detection and analysis

    Maintains both individual delegations and the graph structure
    for efficient invariant checking and concentration analysis.
    """

    def __init__(self) -> None:
        self.delegations: dict[str, dict[str, Any]] = {}
        self.edges: list[DelegationEdge] = []

    def apply_event(self, event: Event) -> None:
        """Apply an event to update projection state"""
        if event.event_type == "DecisionRightDelegated":
            delegation_id = event.payload["delegation_id"]
            self.delegations[delegation_id] = {
                "delegation_id": delegation_id,
                "workspace_id": event.payload["workspace_id"],
                "from_actor": event.payload["from_actor"],
                "to_actor": event.payload["to_actor"],
                "delegated_at": event.payload["delegated_at"],
                "ttl_days": event.payload["ttl_days"],
                "expires_at": event.payload["expires_at"],
                "renewable": event.payload.get("renewable", True),
                "visibility": event.payload.get("visibility", "private"),
                "purpose_tag": event.payload.get("purpose_tag"),
                "is_active": True,
                "revoked_at": None,
                "version": event.version,
            }

            # Add edge for graph analysis
            self.edges.append(
                DelegationEdge(
                    delegation_id=delegation_id,
                    from_actor=event.payload["from_actor"],
                    to_actor=event.payload["to_actor"],
                    workspace_id=event.payload["workspace_id"],
                    expires_at=datetime.fromisoformat(event.payload["expires_at"])
                    if isinstance(event.payload["expires_at"], str)
                    else event.payload["expires_at"],
                    is_active=True,
                )
            )

        elif event.event_type == "DelegationRevoked":
            delegation_id = event.payload["delegation_id"]
            if delegation_id in self.delegations:
                self.delegations[delegation_id]["is_active"] = False
                self.delegations[delegation_id]["revoked_at"] = event.payload["revoked_at"]

                # Update edge
                for edge in self.edges:
                    if edge.delegation_id == delegation_id:
                        edge.is_active = False

        elif event.event_type == "DelegationExpired":
            delegation_id = event.payload["delegation_id"]
            if delegation_id in self.delegations:
                self.delegations[delegation_id]["is_active"] = False

                # Update edge
                for edge in self.edges:
                    if edge.delegation_id == delegation_id:
                        edge.is_active = False

    def get(self, delegation_id: str) -> dict[str, Any] | None:
        """Get delegation by ID"""
        return self.delegations.get(delegation_id)

    def get_active_edges(self, now: datetime) -> list[DelegationEdge]:
        """Get currently active delegation edges"""
        return [edge for edge in self.edges if edge.is_active and edge.expires_at > now]

    def get_delegations_by_actor(self, actor_id: str) -> list[dict[str, Any]]:
        """Get all delegations from an actor"""
        return [
            d
            for d in self.delegations.values()
            if d["from_actor"] == actor_id and d["is_active"]
        ]

    def get_delegations_to_actor(self, actor_id: str) -> list[dict[str, Any]]:
        """Get all delegations to an actor"""
        return [
            d
            for d in self.delegations.values()
            if d["to_actor"] == actor_id and d["is_active"]
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "delegations": self.delegations,
            "edges": [
                {
                    "delegation_id": e.delegation_id,
                    "from_actor": e.from_actor,
                    "to_actor": e.to_actor,
                    "workspace_id": e.workspace_id,
                    "expires_at": e.expires_at.isoformat(),
                    "is_active": e.is_active,
                }
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DelegationGraph":
        """Deserialize from dict"""
        graph = cls()
        graph.delegations = data.get("delegations", {})
        graph.edges = [
            DelegationEdge(
                delegation_id=e["delegation_id"],
                from_actor=e["from_actor"],
                to_actor=e["to_actor"],
                workspace_id=e["workspace_id"],
                expires_at=datetime.fromisoformat(e["expires_at"]),
                is_active=e["is_active"],
            )
            for e in data.get("edges", [])
        ]
        return graph


class LawRegistry:
    """
    Projection: Registry of all laws

    Maintains current state of all laws with efficient lookup
    for activation, review tracking, and querying.
    """

    def __init__(self) -> None:
        self.laws: dict[str, dict[str, Any]] = {}

    def apply_event(self, event: Event) -> None:
        """Apply an event to update projection state"""
        if event.event_type == "LawCreated":
            law_id = event.payload["law_id"]
            self.laws[law_id] = {
                "law_id": law_id,
                "workspace_id": event.payload["workspace_id"],
                "title": event.payload["title"],
                "scope": event.payload.get("scope", {}),
                "reversibility_class": event.payload["reversibility_class"],
                "checkpoints": event.payload["checkpoints"],
                "params": event.payload.get("params", {}),
                "status": "DRAFT",
                "created_at": event.payload["created_at"],
                "created_by": event.payload.get("created_by"),
                "activated_at": None,
                "next_checkpoint_at": None,
                "next_checkpoint_index": 0,
                "version": event.version,
            }

        elif event.event_type == "LawActivated":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                self.laws[law_id]["status"] = "ACTIVE"
                self.laws[law_id]["activated_at"] = event.payload["activated_at"]
                self.laws[law_id]["next_checkpoint_at"] = event.payload[
                    "next_checkpoint_at"
                ]
                self.laws[law_id]["next_checkpoint_index"] = event.payload[
                    "next_checkpoint_index"
                ]
                self.laws[law_id]["version"] = event.version

        elif event.event_type == "LawReviewTriggered":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                self.laws[law_id]["status"] = "REVIEW"
                self.laws[law_id]["review_triggered_at"] = event.payload.get("triggered_at")
                self.laws[law_id]["version"] = event.version

        elif event.event_type == "LawReviewCompleted":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                outcome = event.payload["outcome"]
                if outcome == "continue":
                    self.laws[law_id]["status"] = "ACTIVE"
                    self.laws[law_id]["next_checkpoint_at"] = event.payload.get(
                        "next_checkpoint_at"
                    )
                elif outcome == "adjust":
                    self.laws[law_id]["status"] = "ADJUST"
                elif outcome == "sunset":
                    self.laws[law_id]["status"] = "SUNSET"
                self.laws[law_id]["version"] = event.version

        elif event.event_type == "LawAdjusted":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                self.laws[law_id]["status"] = "ADJUST"
                self.laws[law_id]["version"] = event.version

        elif event.event_type == "LawSunsetScheduled":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                self.laws[law_id]["status"] = "SUNSET"
                self.laws[law_id]["sunset_at"] = event.payload.get("sunset_at")
                self.laws[law_id]["version"] = event.version

        elif event.event_type == "LawArchived":
            law_id = event.payload["law_id"]
            if law_id in self.laws:
                self.laws[law_id]["status"] = "ARCHIVED"
                self.laws[law_id]["archived_at"] = event.payload.get("archived_at")
                self.laws[law_id]["version"] = event.version

    def get(self, law_id: str) -> dict[str, Any] | None:
        """Get law by ID"""
        return self.laws.get(law_id)

    def list_by_status(self, status: LawStatus) -> list[dict[str, Any]]:
        """List laws by status"""
        return [law for law in self.laws.values() if law["status"] == status.value]

    def list_active(self) -> list[dict[str, Any]]:
        """List all active laws"""
        return self.list_by_status(LawStatus.ACTIVE)

    def list_overdue_reviews(self, now: datetime) -> list[dict[str, Any]]:
        """List laws with overdue review checkpoints"""
        overdue = []
        for law in self.laws.values():
            if law["status"] == "ACTIVE" and law["next_checkpoint_at"]:
                checkpoint_dt = (
                    datetime.fromisoformat(law["next_checkpoint_at"])
                    if isinstance(law["next_checkpoint_at"], str)
                    else law["next_checkpoint_at"]
                )
                if now > checkpoint_dt:
                    overdue.append(law)
        return overdue

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {"laws": self.laws}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LawRegistry":
        """Deserialize from dict"""
        registry = cls()
        registry.laws = data.get("laws", {})
        return registry
