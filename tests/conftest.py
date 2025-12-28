"""
Pytest configuration and shared fixtures

Fun fact: The name "conftest" comes from pytest's configuration testing
framework. Files named conftest.py are automatically discovered and their
fixtures are available to all tests in the same directory and subdirectories!
"""

import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pytest

from freedom_that_lasts.kernel.event_store import SQLiteEventStore
from freedom_that_lasts.kernel.projection_store import SQLiteProjectionStore
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.resource.handlers import ResourceCommandHandlers
from freedom_that_lasts.resource.projections import (
    SupplierRegistry,
    TenderRegistry,
    DeliveryLog,
    ProcurementHealthProjection,
)


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Provide a temporary database file that's cleaned up after test"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def event_store(temp_db: Path) -> SQLiteEventStore:
    """Provide a fresh event store for each test"""
    return SQLiteEventStore(temp_db)


@pytest.fixture
def projection_store(temp_db: Path) -> SQLiteProjectionStore:
    """Provide a fresh projection store for each test"""
    return SQLiteProjectionStore(temp_db)


@pytest.fixture
def test_time() -> TestTimeProvider:
    """
    Provide a controllable time provider for deterministic tests

    Default time: 2025-01-15 12:00:00 UTC (chosen because it's a well-known
    Wednesday in the middle of Q1 2025 - perfect for testing fiscal year logic!)
    """
    return TestTimeProvider(datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def safety_policy() -> SafetyPolicy:
    """
    Provide default safety policy for tests

    Fun fact: Safety policies are defense-in-depth mechanisms inspired by
    nuclear reactor safety systems - multiple independent safeguards!
    """
    return SafetyPolicy()


# =============================================================================
# Resource Module Fixtures
# =============================================================================


@pytest.fixture
def resource_handlers(test_time: TestTimeProvider, safety_policy: SafetyPolicy) -> ResourceCommandHandlers:
    """
    Provide resource command handlers for testing

    Handlers are stateless - they take projections as parameters.
    Fun fact: This pattern follows the CQRS principle established by Greg Young in 2010!
    """
    return ResourceCommandHandlers(test_time, safety_policy)


@pytest.fixture
def supplier_registry() -> SupplierRegistry:
    """
    Provide fresh supplier registry projection

    Rebuilt from events for each test - no shared state between tests.
    """
    return SupplierRegistry()


@pytest.fixture
def tender_registry() -> TenderRegistry:
    """
    Provide fresh tender registry projection

    Tracks tender lifecycle from DRAFT → COMPLETED.
    """
    return TenderRegistry()


@pytest.fixture
def delivery_log() -> DeliveryLog:
    """
    Provide fresh delivery log projection

    Tracks milestones and SLA breaches for quality monitoring.
    """
    return DeliveryLog()


@pytest.fixture
def procurement_health() -> ProcurementHealthProjection:
    """
    Provide fresh procurement health projection

    Monitors concentration and feasible set health for anti-capture safeguards.
    """
    return ProcurementHealthProjection()


@pytest.fixture
def mock_law_registry() -> dict:
    """
    Provide mock law registry with one active law

    Minimal viable law for procurement tests - tenders must be linked to laws.
    """
    return {
        "law-123": {
            "law_id": "law-123",
            "workspace_id": "ws-1",
            "title": "Test Procurement Law",
            "status": "ACTIVE",
            "version": 1,
        }
    }


@pytest.fixture
def permissive_safety_policy(safety_policy):
    """
    Safety policy with no reputation threshold for testing selection algorithms

    Disables reputation filtering so tests can focus on rotation/random logic
    without needing to set up supplier reputation scores.
    """
    permissive = SafetyPolicy(
        supplier_min_reputation_threshold=None,  # No reputation filtering
        supplier_share_warn_threshold=safety_policy.supplier_share_warn_threshold,
        supplier_share_halt_threshold=safety_policy.supplier_share_halt_threshold,
    )
    return permissive


@pytest.fixture
def evaluation_time(test_time: TestTimeProvider) -> datetime:
    """
    Provide fixed evaluation time for deterministic feasibility tests

    Uses same time as test_time fixture for consistency.
    Fun fact: Deterministic time is crucial for testing expiration logic!
    """
    return test_time.now()


@pytest.fixture
def valid_supplier() -> dict:
    """
    Provide supplier with valid capabilities for feasibility tests

    Has ISO27001 certification valid for 2025, verified evidence, and capacity.
    """
    return {
        "supplier_id": "s1",
        "name": "Acme Security Corp",
        "capabilities": {
            "ISO27001": {
                "capability_type": "ISO27001",
                "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "evidence": [
                    {
                        "evidence_id": "ev-1",
                        "evidence_type": "certification",
                        "issuer": "ISO Certification Body",
                        "issued_at": datetime(2024, 12, 1, tzinfo=timezone.utc),
                        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                ],
                "verified": True,
                "capacity": {"concurrent_projects": 5, "annual_audits": 20},
            }
        },
        "reputation_score": 0.75,
        "total_value_awarded": Decimal("100000"),
    }


@pytest.fixture
def balanced_suppliers() -> list[dict]:
    """
    Provide three suppliers with balanced loads for rotation testing

    Loads within 10% of each other to test hybrid selection thresholds.
    Fun fact: Load balancing algorithms date back to 1960s mainframe job schedulers!
    """
    return [
        {"supplier_id": "s1", "name": "Supplier One", "total_value_awarded": Decimal("100000"), "reputation_score": 0.8},
        {"supplier_id": "s2", "name": "Supplier Two", "total_value_awarded": Decimal("105000"), "reputation_score": 0.75},
        {"supplier_id": "s3", "name": "Supplier Three", "total_value_awarded": Decimal("95000"), "reputation_score": 0.85},
    ]
