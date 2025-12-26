"""
Integration Tests for Law Lifecycle - Complete Workflows

These tests verify that the entire law lifecycle works end-to-end,
from creation through activation, review, adjustment, and archival.

Fun fact: These are "vertical slice" tests - they exercise the full
stack from command to event to projection, proving the system works!
"""

from datetime import datetime, timedelta, timezone

import pytest

from freedom_that_lasts.kernel.ids import generate_id
from freedom_that_lasts.kernel.safety_policy import SafetyPolicy
from freedom_that_lasts.kernel.time import TestTimeProvider
from freedom_that_lasts.law.commands import (
    ActivateLaw,
    AdjustLaw,
    ArchiveLaw,
    CompleteLawReview,
    CreateLaw,
    CreateWorkspace,
    ScheduleLawSunset,
    TriggerLawReview,
)
from freedom_that_lasts.law.handlers import LawCommandHandlers
from freedom_that_lasts.law.models import LawStatus, ReversibilityClass
from freedom_that_lasts.law.projections import LawRegistry, WorkspaceRegistry


@pytest.fixture
def test_time() -> TestTimeProvider:
    """Provide deterministic time"""
    return TestTimeProvider(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def handlers(test_time: TestTimeProvider) -> LawCommandHandlers:
    """Provide command handlers"""
    return LawCommandHandlers(test_time, SafetyPolicy())


@pytest.fixture
def workspace_registry() -> WorkspaceRegistry:
    """Provide workspace registry"""
    return WorkspaceRegistry()


@pytest.fixture
def law_registry() -> LawRegistry:
    """Provide law registry"""
    return LawRegistry()


def test_complete_law_lifecycle_happy_path(
    handlers: LawCommandHandlers,
    test_time: TestTimeProvider,
    workspace_registry: WorkspaceRegistry,
    law_registry: LawRegistry,
) -> None:
    """
    Test complete law lifecycle: CREATE → ACTIVATE → REVIEW → CONTINUE → ARCHIVE

    This is the "golden path" - a law that works well and continues through reviews.
    """
    # Step 1: Create workspace
    create_ws_cmd = CreateWorkspace(name="Health", scope={"territory": "Budapest"})
    ws_events = handlers.handle_create_workspace(
        create_ws_cmd, command_id=generate_id(), actor_id="alice"
    )

    # Apply events to projection
    for event in ws_events:
        workspace_registry.apply_event(event)

    workspace_id = ws_events[0].payload["workspace_id"]

    # Step 2: Create law
    create_law_cmd = CreateLaw(
        workspace_id=workspace_id,
        title="Primary Care Pilot",
        scope={"territory": "District5"},
        reversibility_class=ReversibilityClass.SEMI_REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={"max_wait_days": 10},
    )
    law_events = handlers.handle_create_law(
        create_law_cmd,
        command_id=generate_id(),
        actor_id="alice",
        workspace_registry=workspace_registry.to_dict()["workspaces"],
    )

    for event in law_events:
        law_registry.apply_event(event)

    law_id = law_events[0].payload["law_id"]

    # Verify law starts in DRAFT
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "DRAFT"

    # Step 3: Activate law
    activate_cmd = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate_cmd,
        command_id=generate_id(),
        actor_id="alice",
        law_registry=law_registry.to_dict()["laws"],
    )

    for event in activate_events:
        law_registry.apply_event(event)

    # Verify law is now ACTIVE with checkpoint scheduled
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ACTIVE"
    assert law["next_checkpoint_at"] is not None

    # Step 4: Advance time to first checkpoint (30 days)
    test_time.advance_days(31)  # Past checkpoint

    # Step 5: Trigger review (would happen automatically in real system)
    review_cmd = TriggerLawReview(law_id=law_id, reason="checkpoint_reached")
    review_events = handlers.handle_trigger_law_review(
        review_cmd,
        command_id=generate_id(),
        actor_id="system",
        law_registry=law_registry.to_dict()["laws"],
    )

    for event in review_events:
        law_registry.apply_event(event)

    # Verify law is now in REVIEW
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "REVIEW"

    # Step 6: Complete review with "continue" outcome
    complete_review_cmd = CompleteLawReview(
        law_id=law_id,
        outcome="continue",
        notes="Pilot performing well, continue as planned",
    )
    complete_events = handlers.handle_complete_law_review(
        complete_review_cmd,
        command_id=generate_id(),
        actor_id="alice",
        law_registry=law_registry.to_dict()["laws"],
    )

    for event in complete_events:
        law_registry.apply_event(event)

    # Verify law returned to ACTIVE with next checkpoint scheduled
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ACTIVE"
    assert law["next_checkpoint_at"] is not None  # Should be 90-day checkpoint now

    # Step 7: Eventually archive law
    archive_cmd = ArchiveLaw(law_id=law_id, reason="Pilot complete, transitioning to permanent policy")
    archive_events = handlers.handle_archive_law(
        archive_cmd,
        command_id=generate_id(),
        actor_id="alice",
        law_registry=law_registry.to_dict()["laws"],
    )

    for event in archive_events:
        law_registry.apply_event(event)

    # Verify law is ARCHIVED
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ARCHIVED"


def test_law_lifecycle_with_adjustment(
    handlers: LawCommandHandlers,
    test_time: TestTimeProvider,
    workspace_registry: WorkspaceRegistry,
    law_registry: LawRegistry,
) -> None:
    """
    Test law lifecycle with adjustment: CREATE → ACTIVATE → REVIEW → ADJUST → ACTIVE

    This tests the scenario where a law needs modifications during review.
    """
    # Setup: Create workspace and law, activate it
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    create_law = CreateLaw(
        workspace_id=workspace_id,
        title="Test Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={"initial_param": 100},
    )
    law_events = handlers.handle_create_law(
        create_law, generate_id(), "alice", workspace_registry.to_dict()["workspaces"]
    )
    for event in law_events:
        law_registry.apply_event(event)
    law_id = law_events[0].payload["law_id"]

    activate = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in activate_events:
        law_registry.apply_event(event)

    # Advance time and trigger review
    test_time.advance_days(31)

    review = TriggerLawReview(law_id=law_id, reason="checkpoint")
    review_events = handlers.handle_trigger_law_review(
        review, generate_id(), "system", law_registry.to_dict()["laws"]
    )
    for event in review_events:
        law_registry.apply_event(event)

    # Complete review with "adjust" outcome
    complete = CompleteLawReview(
        law_id=law_id,
        outcome="adjust",
        notes="Needs parameter tuning",
    )
    complete_events = handlers.handle_complete_law_review(
        complete, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in complete_events:
        law_registry.apply_event(event)

    # Verify law is in ADJUST status
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ADJUST"

    # Apply adjustment
    adjust = AdjustLaw(
        law_id=law_id,
        changes={"initial_param": 150},  # Increase parameter
        reason="Review feedback indicated need for higher threshold",
    )
    adjust_events = handlers.handle_adjust_law(
        adjust, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in adjust_events:
        law_registry.apply_event(event)

    # Verify law returned to ACTIVE
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ACTIVE"
    assert law["next_checkpoint_at"] is not None


def test_law_lifecycle_with_sunset(
    handlers: LawCommandHandlers,
    test_time: TestTimeProvider,
    workspace_registry: WorkspaceRegistry,
    law_registry: LawRegistry,
) -> None:
    """
    Test law lifecycle with sunset: CREATE → ACTIVATE → REVIEW → SUNSET → ARCHIVE

    This tests the scenario where a law is scheduled for termination.
    """
    # Setup: Create workspace and law, activate it
    create_ws = CreateWorkspace(name="Health", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    create_law = CreateLaw(
        workspace_id=workspace_id,
        title="Pilot Program",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={},
    )
    law_events = handlers.handle_create_law(
        create_law, generate_id(), "alice", workspace_registry.to_dict()["workspaces"]
    )
    for event in law_events:
        law_registry.apply_event(event)
    law_id = law_events[0].payload["law_id"]

    activate = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in activate_events:
        law_registry.apply_event(event)

    # Complete review with "sunset" outcome
    test_time.advance_days(31)

    review = TriggerLawReview(law_id=law_id, reason="checkpoint")
    review_events = handlers.handle_trigger_law_review(
        review, generate_id(), "system", law_registry.to_dict()["laws"]
    )
    for event in review_events:
        law_registry.apply_event(event)

    complete = CompleteLawReview(
        law_id=law_id,
        outcome="sunset",
        notes="Pilot objectives achieved, transitioning to permanent policy",
    )
    complete_events = handlers.handle_complete_law_review(
        complete, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in complete_events:
        law_registry.apply_event(event)

    # Verify law is in SUNSET status
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "SUNSET"

    # Schedule sunset
    schedule_sunset = ScheduleLawSunset(
        law_id=law_id,
        sunset_days=30,
        reason="30-day wind-down period",
    )
    sunset_events = handlers.handle_schedule_law_sunset(
        schedule_sunset, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in sunset_events:
        law_registry.apply_event(event)

    # Finally archive
    archive = ArchiveLaw(law_id=law_id, reason="Sunset period complete")
    archive_events = handlers.handle_archive_law(
        archive, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in archive_events:
        law_registry.apply_event(event)

    # Verify law is ARCHIVED
    law = law_registry.get(law_id)
    assert law is not None
    assert law["status"] == "ARCHIVED"


def test_overdue_reviews_query(
    handlers: LawCommandHandlers,
    test_time: TestTimeProvider,
    workspace_registry: WorkspaceRegistry,
    law_registry: LawRegistry,
) -> None:
    """
    Test that we can query for laws with overdue reviews

    This is critical for automatic review triggers.
    """
    # Create workspace
    create_ws = CreateWorkspace(name="Test", scope={})
    ws_events = handlers.handle_create_workspace(create_ws, generate_id(), "alice")
    for event in ws_events:
        workspace_registry.apply_event(event)
    workspace_id = ws_events[0].payload["workspace_id"]

    # Create and activate law
    create_law = CreateLaw(
        workspace_id=workspace_id,
        title="Test Law",
        scope={},
        reversibility_class=ReversibilityClass.REVERSIBLE,
        checkpoints=[30, 90, 180, 365],
        params={},
    )
    law_events = handlers.handle_create_law(
        create_law, generate_id(), "alice", workspace_registry.to_dict()["workspaces"]
    )
    for event in law_events:
        law_registry.apply_event(event)
    law_id = law_events[0].payload["law_id"]

    activate = ActivateLaw(law_id=law_id)
    activate_events = handlers.handle_activate_law(
        activate, generate_id(), "alice", law_registry.to_dict()["laws"]
    )
    for event in activate_events:
        law_registry.apply_event(event)

    # Verify no overdue reviews yet
    overdue = law_registry.list_overdue_reviews(test_time.now())
    assert len(overdue) == 0

    # Advance time past checkpoint
    test_time.advance_days(35)  # 5 days overdue

    # Verify law now shows as overdue
    overdue = law_registry.list_overdue_reviews(test_time.now())
    assert len(overdue) == 1
    assert overdue[0]["law_id"] == law_id
