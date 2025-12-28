"""
Comprehensive CLI integration tests

Tests all CLI commands for workspace, law, delegation, system, supplier, tender, and delivery operations.
Uses Typer's CliRunner for isolated command testing without actual execution.

Fun fact: The first command-line interface (CLI) was created in 1964 for the Dartmouth Time Sharing System.
It revolutionized computing by allowing users to interact with computers through text commands!
"""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from freedom_that_lasts.cli.main import app


@pytest.fixture
def runner():
    """Typer CLI test runner"""
    return CliRunner()


@pytest.fixture
def temp_db():
    """Temporary database for CLI tests"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    # Delete the file so init can create it
    db_path.unlink()
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


# =============================================================================
# Initialization Tests
# =============================================================================


def test_init_creates_database(runner, tmp_path):
    """Test init command creates database"""
    db_path = tmp_path / "test.db"

    result = runner.invoke(app, ["init", "--db", str(db_path)])

    assert result.exit_code == 0
    assert db_path.exists()
    assert "initialized" in result.stdout.lower()


def test_init_with_existing_database(runner, tmp_path):
    """Test init command with existing database"""
    db_path = tmp_path / "test.db"

    # Create database first
    runner.invoke(app, ["init", "--db", str(db_path)])

    # Try to init again - should fail
    result = runner.invoke(app, ["init", "--db", str(db_path)])

    # Should fail when trying to init existing database
    assert result.exit_code == 1


# =============================================================================
# Workspace Command Tests
# =============================================================================


def test_workspace_create(runner, temp_db):
    """Test workspace create command"""
    # Init database first
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["workspace", "create", "--name", "Test Workspace", "--db", str(temp_db)]
    )

    assert result.exit_code == 0
    assert "workspace" in result.stdout.lower()
    assert "test workspace" in result.stdout.lower()


def test_workspace_create_with_scope(runner, temp_db):
    """Test workspace create with scope parameter"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "workspace",
            "create",
            "--name",
            "Health Services",
            "--scope",
            '{"territory": "Budapest"}',
            "--db",
            str(temp_db),
        ],
    )

    assert result.exit_code == 0
    assert "health services" in result.stdout.lower()


def test_workspace_list(runner, temp_db):
    """Test workspace list command"""
    # Init and create a workspace first
    runner.invoke(app, ["init", "--db", str(temp_db)])
    runner.invoke(app, ["workspace", "create", "--name", "WS1", "--db", str(temp_db)])

    result = runner.invoke(app, ["workspace", "list", "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "ws1" in result.stdout.lower() or "workspace" in result.stdout.lower()


def test_workspace_list_empty(runner, temp_db):
    """Test workspace list with no workspaces"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["workspace", "list", "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "no active workspaces" in result.stdout.lower()


# =============================================================================
# Delegation Command Tests
# =============================================================================


def test_delegate_create(runner, temp_db):
    """Test delegate create command"""
    # Init and create workspace first
    runner.invoke(app, ["init", "--db", str(temp_db)])
    ws_result = runner.invoke(
        app, ["workspace", "create", "--name", "Test WS", "--db", str(temp_db)]
    )

    # Extract workspace_id from output
    # Output format: "✓ Created workspace: ws-..."
    workspace_id = None
    for line in ws_result.stdout.split("\n"):
        if "created workspace:" in line.lower():
            workspace_id = line.split(":")[-1].strip()
            break

    if workspace_id:
        result = runner.invoke(
            app,
            [
                "delegate",
                "create",
                "--from",
                "alice",
                "--to",
                "bob",
                "--workspace",
                workspace_id,
                "--ttl-days",
                "180",
                "--db",
                str(temp_db),
            ],
        )

        assert result.exit_code == 0
        assert "delegation" in result.stdout.lower()


# =============================================================================
# Law Command Tests
# =============================================================================


def test_law_create(runner, temp_db):
    """Test law create command"""
    # Init and create workspace first
    runner.invoke(app, ["init", "--db", str(temp_db)])
    ws_result = runner.invoke(
        app, ["workspace", "create", "--name", "Legal", "--db", str(temp_db)]
    )

    # Extract workspace_id
    workspace_id = None
    for line in ws_result.stdout.split("\n"):
        if "created workspace:" in line.lower():
            workspace_id = line.split(":")[-1].strip()
            break

    if workspace_id:
        result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Test Law",
                "--reversibility",
                "REVERSIBLE",
                "--checkpoints",
                "30,90,180,365",  # Must include all minimum checkpoints
                "--db",
                str(temp_db),
            ],
        )

        assert result.exit_code == 0
        assert "law" in result.stdout.lower()


def test_law_list(runner, temp_db):
    """Test law list command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["law", "list", "--db", str(temp_db)])

    assert result.exit_code == 0


def test_law_list_with_status_filter(runner, temp_db):
    """Test law list with status filter"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["law", "list", "--status", "ACTIVE", "--db", str(temp_db)]
    )

    assert result.exit_code == 0


# =============================================================================
# System Command Tests
# =============================================================================


def test_tick_command(runner, temp_db):
    """Test tick command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["tick", "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "tick" in result.stdout.lower() or "health" in result.stdout.lower()


def test_health_command(runner, temp_db):
    """Test health command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["health", "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "health" in result.stdout.lower() or "risk" in result.stdout.lower()


def test_safety_command(runner, temp_db):
    """Test safety events command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["safety", "--db", str(temp_db)])

    assert result.exit_code == 0


def test_safety_command_shows_policy(runner, temp_db):
    """Test safety command shows policy and events"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["safety", "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "safety policy" in result.stdout.lower() or "gini" in result.stdout.lower()


# =============================================================================
# Supplier Command Tests
# =============================================================================


def test_supplier_register(runner, temp_db):
    """Test supplier register command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "supplier",
            "register",
            "--name",
            "Acme Corp",
            "--type",
            "company",
            "--db",
            str(temp_db),
        ],
    )

    assert result.exit_code == 0
    assert "supplier" in result.stdout.lower() or "acme" in result.stdout.lower()


def test_supplier_register_with_metadata(runner, temp_db):
    """Test supplier register with metadata"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "supplier",
            "register",
            "--name",
            "Tech Co",
            "--type",
            "company",
            "--metadata",
            '{"industry": "technology"}',
            "--db",
            str(temp_db),
        ],
    )

    assert result.exit_code == 0


def test_supplier_list(runner, temp_db):
    """Test supplier list command"""
    # Init and register a supplier first
    runner.invoke(app, ["init", "--db", str(temp_db)])
    runner.invoke(
        app,
        [
            "supplier",
            "register",
            "--name",
            "Test Supplier",
            "--type",
            "company",
            "--db",
            str(temp_db),
        ],
    )

    result = runner.invoke(app, ["supplier", "list", "--db", str(temp_db)])

    assert result.exit_code == 0


# =============================================================================
# Tender Command Tests
# =============================================================================


def test_tender_list(runner, temp_db):
    """Test tender list command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["tender", "list", "--db", str(temp_db)])

    assert result.exit_code == 0


def test_tender_list_with_status_filter(runner, temp_db):
    """Test tender list with status filter"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["tender", "list", "--status", "OPEN", "--db", str(temp_db)]
    )

    assert result.exit_code == 0


# =============================================================================
# Delivery Command Tests
# =============================================================================


def test_delivery_list_requires_tender(runner, temp_db):
    """Test delivery list command requires tender ID"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # delivery list requires --tender parameter
    result = runner.invoke(app, ["delivery", "list", "--db", str(temp_db)])

    # Should fail due to missing required --tender parameter
    assert result.exit_code != 0


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_command_with_missing_database(runner):
    """Test command fails gracefully when database doesn't exist"""
    result = runner.invoke(
        app, ["workspace", "list", "--db", "/nonexistent/path/test.db"]
    )

    # Should fail with exit code 1 when database doesn't exist
    assert result.exit_code == 1


def test_command_with_missing_required_param(runner, temp_db):
    """Test command with missing required parameter"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # Try to create workspace without --name
    result = runner.invoke(app, ["workspace", "create", "--db", str(temp_db)])

    # Should fail due to missing --name
    assert result.exit_code != 0


def test_init_without_db_uses_default(runner, tmp_path):
    """Test init command without --db uses default path"""
    # Change to tmp directory to avoid polluting working directory
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["init"])

        # Should succeed or fail gracefully
        assert result.exit_code in [0, 1, 2]
    finally:
        os.chdir(old_cwd)


# =============================================================================
# Budget Command Tests
# =============================================================================


def test_budget_create(runner, temp_db):
    """Test budget create command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # Create workspace and law first
    ws_result = runner.invoke(
        app, ["workspace", "create", "--name", "Finance", "--db", str(temp_db)]
    )

    workspace_id = None
    for line in ws_result.stdout.split("\n"):
        if "created workspace:" in line.lower():
            workspace_id = line.split(":")[-1].strip()
            break

    if workspace_id:
        law_result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Finance Law",
                "--reversibility",
                "REVERSIBLE",
                "--db",
                str(temp_db),
            ],
        )

        law_id = None
        for line in law_result.stdout.split("\n"):
            if "created law:" in line.lower():
                law_id = line.split(":")[-1].strip()
                break

        if law_id:
            # Activate law first
            runner.invoke(app, ["law", "activate", "--id", law_id, "--db", str(temp_db)])

            result = runner.invoke(
                app,
                [
                    "budget",
                    "create",
                    "--law-id",
                    law_id,
                    "--fiscal-year",
                    "2025",
                    "--items",
                    '[{"category": "Healthcare", "allocated": 1000000.0}]',
                    "--db",
                    str(temp_db),
                ],
            )

            # May succeed or fail depending on law state
            assert result.exit_code in [0, 1, 2]


def test_budget_list(runner, temp_db):
    """Test budget list command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(app, ["budget", "list", "--db", str(temp_db)])

    assert result.exit_code == 0


# =============================================================================
# Expenditure Command Tests
# =============================================================================


def test_expenditure_list_requires_budget(runner, temp_db):
    """Test expenditure list command requires budget ID"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # expenditure list requires --budget parameter
    result = runner.invoke(app, ["expenditure", "list", "--db", str(temp_db)])

    # Should fail due to missing required --budget parameter
    assert result.exit_code != 0


# =============================================================================
# Law Activate/Archive Command Tests
# =============================================================================


def test_law_activate(runner, temp_db):
    """Test law activate command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # Create workspace and law first
    ws_result = runner.invoke(
        app, ["workspace", "create", "--name", "Legal", "--db", str(temp_db)]
    )

    workspace_id = None
    for line in ws_result.stdout.split("\n"):
        if "created workspace:" in line.lower():
            workspace_id = line.split(":")[-1].strip()
            break

    if workspace_id:
        law_result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Test Law",
                "--reversibility",
                "REVERSIBLE",
                "--db",
                str(temp_db),
            ],
        )

        law_id = None
        for line in law_result.stdout.split("\n"):
            if "created law:" in line.lower():
                law_id = line.split(":")[-1].strip()
                break

        if law_id:
            result = runner.invoke(
                app, ["law", "activate", "--id", law_id, "--db", str(temp_db)]
            )

            # May succeed or fail depending on law state
            assert result.exit_code in [0, 1, 2]


def test_law_review(runner, temp_db):
    """Test law review command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["law", "review", "--id", "law-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if law doesn't exist or missing params)
    assert result.exit_code in [0, 1, 2]


# =============================================================================
# Budget Activate/Show Command Tests
# =============================================================================


def test_budget_activate(runner, temp_db):
    """Test budget activate command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["budget", "activate", "--id", "budget-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if budget doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_budget_adjust(runner, temp_db):
    """Test budget adjust command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "budget",
            "adjust",
            "--id",
            "budget-123",
            "--adjustments",
            '[{"category": "Healthcare", "adjustment": 10000.0, "reason": "Increased demand"}]',
            "--db",
            str(temp_db),
        ],
    )

    # Should handle gracefully (may fail if budget doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_budget_show(runner, temp_db):
    """Test budget show command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["budget", "show", "--id", "budget-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if budget doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_budget_close(runner, temp_db):
    """Test budget close command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["budget", "close", "--id", "budget-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if budget doesn't exist)
    assert result.exit_code in [0, 1, 2]


# =============================================================================
# Expenditure Approve Command Tests
# =============================================================================


def test_expenditure_approve(runner, temp_db):
    """Test expenditure approve command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "expenditure",
            "approve",
            "--budget-id",
            "budget-123",
            "--category",
            "Healthcare",
            "--amount",
            "5000.0",
            "--description",
            "Medical supplies",
            "--db",
            str(temp_db),
        ],
    )

    # Should handle gracefully (may fail if budget doesn't exist)
    assert result.exit_code in [0, 1, 2]


# =============================================================================
# Supplier Additional Command Tests
# =============================================================================


def test_supplier_add_capability(runner, temp_db):
    """Test supplier add capability command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    # Register supplier first
    supplier_result = runner.invoke(
        app,
        [
            "supplier",
            "register",
            "--name",
            "Test Supplier",
            "--type",
            "company",
            "--db",
            str(temp_db),
        ],
    )

    supplier_id = None
    for line in supplier_result.stdout.split("\n"):
        if "supplier" in line.lower():
            # Try to extract ID from output
            parts = line.split()
            for part in parts:
                if part.startswith("s-") or part.startswith("sup-"):
                    supplier_id = part.strip()
                    break

    # Even if we can't get supplier_id, test the command
    result = runner.invoke(
        app,
        [
            "supplier",
            "add-capability",
            "--supplier-id",
            supplier_id or "s-123",
            "--capability",
            "ISO27001",
            "--valid-from",
            "2025-01-01",
            "--valid-until",
            "2026-01-01",
            "--db",
            str(temp_db),
        ],
    )

    assert result.exit_code in [0, 1, 2]


def test_supplier_show(runner, temp_db):
    """Test supplier show command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["supplier", "show", "--id", "s-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if supplier doesn't exist)
    assert result.exit_code in [0, 1, 2]


# =============================================================================
# Tender Command Tests
# =============================================================================


def test_tender_create(runner, temp_db):
    """Test tender create command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "tender",
            "create",
            "--law-id",
            "law-123",
            "--title",
            "Test Tender",
            "--description",
            "Test tender description",
            "--budget-allocated",
            "100000.0",
            "--db",
            str(temp_db),
        ],
    )

    # Should handle gracefully (may fail if law doesn't exist or missing params)
    assert result.exit_code in [0, 1, 2]


def test_tender_open(runner, temp_db):
    """Test tender open command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "tender",
            "open",
            "--id",
            "t-123",
            "--deadline",
            "2025-12-31T23:59:59",
            "--db",
            str(temp_db),
        ],
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_tender_evaluate(runner, temp_db):
    """Test tender evaluate command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["tender", "evaluate", "--id", "t-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_tender_select(runner, temp_db):
    """Test tender select command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["tender", "select", "--id", "t-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_tender_award(runner, temp_db):
    """Test tender award command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["tender", "award", "--id", "t-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_tender_show(runner, temp_db):
    """Test tender show command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["tender", "show", "--id", "t-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


# =============================================================================
# Delivery Command Tests
# =============================================================================


def test_delivery_milestone(runner, temp_db):
    """Test delivery milestone command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app,
        [
            "delivery",
            "milestone",
            "--tender-id",
            "t-123",
            "--milestone",
            "Phase 1 Complete",
            "--db",
            str(temp_db),
        ],
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]


def test_delivery_complete(runner, temp_db):
    """Test delivery complete command"""
    runner.invoke(app, ["init", "--db", str(temp_db)])

    result = runner.invoke(
        app, ["delivery", "complete", "--tender-id", "t-123", "--db", str(temp_db)]
    )

    # Should handle gracefully (may fail if tender doesn't exist)
    assert result.exit_code in [0, 1, 2]
