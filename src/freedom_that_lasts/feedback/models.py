"""
Feedback Module Models - Risk levels and warning/halt events

These models define the health indicators and automatic responses
that protect the system from tyranny.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """
    Overall system risk level

    GREEN: System healthy, all safeguards within normal bounds
    YELLOW: Warning thresholds breached, attention required
    RED: Halt thresholds breached, automatic safeguards engaged
    """

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ConcentrationMetrics(BaseModel):
    """
    Delegation concentration metrics

    Measures how evenly distributed decision-making power is.
    High concentration = power entrenchment risk.
    """

    gini_coefficient: float = Field(
        ge=0.0,
        le=1.0,
        description="Gini coefficient (0=perfect equality, 1=total concentration)",
    )
    max_in_degree: int = Field(
        ge=0,
        description="Maximum delegations received by single actor",
    )
    total_active_delegations: int = Field(
        ge=0,
        description="Total active delegations in system",
    )
    unique_delegates: int = Field(
        ge=0,
        description="Number of unique actors receiving delegations",
    )


class LawReviewHealth(BaseModel):
    """
    Law review checkpoint health metrics

    Tracks whether laws are being reviewed on schedule.
    Overdue reviews = drift risk.
    """

    total_active_laws: int = Field(ge=0)
    overdue_reviews: int = Field(ge=0)
    upcoming_reviews_7d: int = Field(
        ge=0,
        description="Reviews due in next 7 days",
    )
    upcoming_reviews_30d: int = Field(
        ge=0,
        description="Reviews due in next 30 days",
    )


class FreedomHealthScore(BaseModel):
    """
    Overall freedom health scorecard

    Combines all risk indicators into a unified view.
    This is what users/operators see to understand system health.
    """

    risk_level: RiskLevel
    concentration: ConcentrationMetrics
    law_review_health: LawReviewHealth
    reasons: list[str] = Field(
        default_factory=list,
        description="Machine-readable reasons for current risk level",
    )
    computed_at: datetime


class WarningReason(BaseModel):
    """Structured warning reason"""

    category: str  # "delegation_concentration", "law_review_overdue", etc.
    severity: str  # "warning", "halt"
    message: str
    context: dict = Field(default_factory=dict)


class HaltCondition(BaseModel):
    """Halt condition details"""

    trigger_type: str  # "delegation_gini", "delegation_in_degree", etc.
    threshold_value: float | int
    actual_value: float | int
    triggered_at: datetime
    automatic_responses: list[str] = Field(
        default_factory=list,
        description="Automatic safeguards engaged (transparency_escalation, etc.)",
    )
