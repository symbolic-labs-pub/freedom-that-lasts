"""
Law Module - Decision rights, delegation, and law lifecycle

This module implements the core governance mechanics:
- Hierarchical workspaces (scopes of authority)
- Revocable delegation with TTL (temporary authority transfer)
- Time-bound laws with mandatory review checkpoints
- Acyclic delegation DAG (prevents power loops)

Fun fact: The delegation DAG is inspired by certificate chains in PKI,
but adapted for human authority delegation rather than cryptographic trust!
"""

from freedom_that_lasts.law.models import (
    Delegation,
    Law,
    LawStatus,
    ReversibilityClass,
    Workspace,
)

__all__ = [
    "Workspace",
    "Delegation",
    "Law",
    "LawStatus",
    "ReversibilityClass",
]
