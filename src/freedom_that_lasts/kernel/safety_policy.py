"""
Safety Policy - Constitutional parameters for anti-tyranny safeguards

The SafetyPolicy defines the thresholds and constraints that protect
the system from power entrenchment, irreversible drift, and coercion.

Fun fact: These parameters are like the "physical constants" of the governance
universe - they define the boundaries within which freedom remains stable!
"""

from typing import Literal

from pydantic import BaseModel, Field


class SafetyPolicy(BaseModel):
    """
    Constitutional safety parameters

    These parameters control the system's anti-tyranny safeguards.
    Changes to safety policy are evented and versioned, preventing
    silent weakening of protections.

    The default values are derived from the book's appendices and
    represent conservative thresholds that prioritize option-space
    preservation over expedience.
    """

    policy_version: str = Field(
        default="1.0",
        description="Policy version for tracking changes over time",
    )

    # Delegation concentration safeguards (anti-entrenchment)
    delegation_gini_warn: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="Gini coefficient warning threshold for delegation concentration",
    )

    delegation_gini_halt: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Gini coefficient halt threshold (triggers expansion freeze)",
    )

    delegation_in_degree_warn: int = Field(
        default=500,
        ge=1,
        description="Warning threshold for maximum delegations to single actor",
    )

    delegation_in_degree_halt: int = Field(
        default=2000,
        ge=1,
        description="Halt threshold for maximum delegations (triggers safeguards)",
    )

    # Delegation TTL (anti-permanent-authority)
    max_delegation_ttl_days: int = Field(
        default=365,
        ge=1,
        le=3650,  # Max 10 years seems reasonable upper bound
        description="Maximum days a delegation can last before renewal required",
    )

    delegation_requires_renewal: bool = Field(
        default=True,
        description="Whether delegations must be explicitly renewed (vs auto-renew)",
    )

    # Law lifecycle safeguards
    law_max_active_days_without_review: int = Field(
        default=365,
        ge=1,
        description="Maximum days a law can be active without mandatory review",
    )

    law_min_checkpoint_schedule: list[int] = Field(
        default=[30, 90, 180, 365],
        description="Minimum checkpoint schedule (days) for active laws",
    )

    # Privacy & coercion resistance
    delegation_visibility_default: Literal["private", "org_only", "public"] = Field(
        default="private",
        description="Default visibility for delegation edges (privacy-by-default)",
    )

    forbid_vote_proof_artifacts: bool = Field(
        default=True,
        description="Prevent creation of artifacts that prove how someone voted",
    )

    # Transparency escalation (anti-tyranny reflex)
    transparency_escalation_enabled: bool = Field(
        default=True,
        description="Enable automatic transparency escalation on HALT conditions",
    )

    transparency_escalation_on_halt: bool = Field(
        default=True,
        description="Escalate transparency when HALT thresholds breached",
    )

    # Budget safeguards (anti-manipulation)
    budget_step_size_limits: dict[str, float] = Field(
        default={
            "CRITICAL": 0.05,  # 5% max change per adjustment
            "IMPORTANT": 0.15,  # 15% max change per adjustment
            "ASPIRATIONAL": 0.50,  # 50% max change per adjustment
        },
        description="Maximum percentage change per adjustment by flex class",
    )

    budget_balance_enforcement: Literal["STRICT", "RELAXED"] = Field(
        default="STRICT",
        description="Budget balance mode: STRICT (zero-sum) or RELAXED (allow variance)",
    )

    budget_critical_concentration_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Warning threshold for CRITICAL items concentration (% of total)",
    )

    model_config = {
        "frozen": False,  # Policy can be updated (but changes are evented)
        "json_schema_extra": {
            "description": "Constitutional safety parameters governing anti-tyranny safeguards"
        },
    }

    def validate_checkpoint_schedule(self, checkpoints: list[int]) -> bool:
        """
        Check if checkpoint schedule meets minimum requirements

        Args:
            checkpoints: Proposed checkpoint schedule (days)

        Returns:
            True if schedule meets minimum requirements
        """
        if not checkpoints:
            return False

        # Check that all minimum checkpoints are covered
        tolerance_days = 5
        for min_checkpoint in self.law_min_checkpoint_schedule:
            # Find any checkpoint within tolerance of min_checkpoint
            # (can be before or after)
            found = any(
                abs(cp - min_checkpoint) <= tolerance_days for cp in checkpoints
            )
            if not found:
                return False

        return True


# Default global policy instance
default_safety_policy = SafetyPolicy()
