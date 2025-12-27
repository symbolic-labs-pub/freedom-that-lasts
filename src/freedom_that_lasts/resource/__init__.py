"""
Resource & Procurement Module

Evidence-based capability registry with constitutional supplier selection.
Binary requirement matching (no scoring), rotation/random selection mechanisms,
and supplier concentration monitoring for structural procurement capture resistance.

Fun fact: The ancient Roman Republic used sortition (random selection by lottery)
for some offices to prevent corruption - we're bringing that wisdom into
procurement with cryptographically auditable randomness!
"""

from freedom_that_lasts.resource.commands import (
    AddCapabilityClaim,
    AwardTender,
    CancelTender,
    CompleteTender,
    CreateTender,
    EvaluateTender,
    OpenTender,
    RecordMilestone,
    RecordSLABreach,
    RegisterSupplier,
    RevokeCapabilityClaim,
    SelectSupplier,
    UpdateCapabilityClaim,
)
from freedom_that_lasts.resource.events import (
    CapabilityClaimAdded,
    CapabilityClaimRevoked,
    CapabilityClaimUpdated,
    EmptyFeasibleSetDetected,
    FeasibleSetComputed,
    MilestoneRecorded,
    ReputationUpdated,
    SLABreachDetected,
    SupplierConcentrationHalt,
    SupplierConcentrationWarning,
    SupplierRegistered,
    SupplierSelected,
    SupplierSelectionFailed,
    TenderAwarded,
    TenderCancelled,
    TenderCompleted,
    TenderCreated,
    TenderOpened,
)
from freedom_that_lasts.resource.models import (
    CapabilityClaim,
    Evidence,
    SelectionMethod,
    Supplier,
    Tender,
    TenderRequirement,
    TenderStatus,
)

# Handlers and projections will be imported when they're implemented
# from freedom_that_lasts.resource.handlers import ResourceCommandHandlers
# from freedom_that_lasts.resource.projections import (
#     DeliveryLog,
#     ProcurementHealthProjection,
#     SupplierRegistry,
#     TenderRegistry,
# )

__all__ = [
    # Models
    "Evidence",
    "CapabilityClaim",
    "Supplier",
    "TenderRequirement",
    "Tender",
    "TenderStatus",
    "SelectionMethod",
    # Commands
    "RegisterSupplier",
    "AddCapabilityClaim",
    "UpdateCapabilityClaim",
    "RevokeCapabilityClaim",
    "CreateTender",
    "OpenTender",
    "EvaluateTender",
    "SelectSupplier",
    "AwardTender",
    "CancelTender",
    "RecordMilestone",
    "RecordSLABreach",
    "CompleteTender",
    # Events
    "SupplierRegistered",
    "CapabilityClaimAdded",
    "CapabilityClaimUpdated",
    "CapabilityClaimRevoked",
    "TenderCreated",
    "TenderOpened",
    "FeasibleSetComputed",
    "SupplierSelected",
    "SupplierSelectionFailed",
    "TenderAwarded",
    "TenderCancelled",
    "MilestoneRecorded",
    "SLABreachDetected",
    "TenderCompleted",
    "ReputationUpdated",
    "EmptyFeasibleSetDetected",
    "SupplierConcentrationWarning",
    "SupplierConcentrationHalt",
    # Handlers (to be added)
    # "ResourceCommandHandlers",
    # Projections (to be added)
    # "SupplierRegistry",
    # "TenderRegistry",
    # "DeliveryLog",
    # "ProcurementHealthProjection",
]
