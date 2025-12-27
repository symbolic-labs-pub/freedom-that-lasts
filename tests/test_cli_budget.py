"""
CLI Integration Tests for Budget Commands

Tests the budget and expenditure CLI commands end-to-end.
"""

import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from freedom_that_lasts.cli.main import app

runner = CliRunner()


def test_budget_full_lifecycle_via_cli():
    """Test complete budget lifecycle through CLI commands"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Initialize database
        result = runner.invoke(app, ["init", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "Initialized FTL database" in result.stdout

        # Create workspace
        result = runner.invoke(
            app, ["workspace", "create", "--name", "Health", "--db", str(db_path)]
        )
        assert result.exit_code == 0
        workspace_id = result.stdout.split("workspace: ")[1].split("\n")[0]

        # Create law
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
                "SEMI_REVERSIBLE",
                "--scope",
                '{"description": "Test"}',
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        law_id = result.stdout.split("law: ")[1].split("\n")[0]

        # Activate law
        result = runner.invoke(
            app, ["law", "activate", "--id", law_id, "--db", str(db_path)]
        )
        assert result.exit_code == 0

        # Create budget
        budget_items = json.dumps(
            [
                {
                    "name": "Staff",
                    "allocated_amount": "100000",
                    "flex_class": "CRITICAL",
                    "category": "personnel",
                },
                {
                    "name": "Equipment",
                    "allocated_amount": "50000",
                    "flex_class": "IMPORTANT",
                    "category": "capital",
                },
            ]
        )
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
                budget_items,
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Created budget:" in result.stdout
        assert "Total: $150000" in result.stdout
        budget_id = result.stdout.split("budget: ")[1].split("\n")[0]

        # Show budget
        result = runner.invoke(
            app, ["budget", "show", "--id", budget_id, "--db", str(db_path)]
        )
        assert result.exit_code == 0
        assert "Staff [CRITICAL]" in result.stdout
        assert "Equipment [IMPORTANT]" in result.stdout
        assert "Allocated: $100000" in result.stdout

        # List budgets
        result = runner.invoke(app, ["budget", "list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "Budgets (1):" in result.stdout
        assert budget_id in result.stdout

        # Activate budget
        result = runner.invoke(
            app, ["budget", "activate", "--id", budget_id, "--db", str(db_path)]
        )
        assert result.exit_code == 0
        assert "Activated budget:" in result.stdout
        assert "Status: ACTIVE" in result.stdout

        # Get item IDs from JSON output
        result = runner.invoke(
            app, ["budget", "show", "--id", budget_id, "--json", "--db", str(db_path)]
        )
        assert result.exit_code == 0
        budget_data = json.loads(result.stdout)
        staff_item_id = [
            item_id
            for item_id, item in budget_data["items"].items()
            if item["name"] == "Staff"
        ][0]

        # Approve expenditure
        result = runner.invoke(
            app,
            [
                "expenditure",
                "approve",
                "--budget",
                budget_id,
                "--item",
                staff_item_id,
                "--amount",
                "25000",
                "--purpose",
                "Hire analyst",
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Approved expenditure: $25000" in result.stdout
        assert "Staff" in result.stdout
        assert "Hire analyst" in result.stdout

        # List expenditures
        result = runner.invoke(
            app,
            [
                "expenditure",
                "list",
                "--budget",
                budget_id,
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Expenditures (1):" in result.stdout
        assert "$25000" in result.stdout
        assert "Hire analyst" in result.stdout

        # Close budget
        result = runner.invoke(
            app,
            [
                "budget",
                "close",
                "--id",
                budget_id,
                "--reason",
                "End of fiscal year",
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Closed budget:" in result.stdout
        assert "Status: CLOSED" in result.stdout


def test_budget_list_filters():
    """Test budget list filtering by law and status"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Initialize
        runner.invoke(app, ["init", "--db", str(db_path)])

        # Create workspace and law
        result = runner.invoke(
            app, ["workspace", "create", "--name", "Test", "--db", str(db_path)]
        )
        workspace_id = result.stdout.split("workspace: ")[1].split("\n")[0]

        result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Law 1",
                "--reversibility",
                "SEMI_REVERSIBLE",
                "--db",
                str(db_path),
            ],
        )
        law_id = result.stdout.split("law: ")[1].split("\n")[0]

        # Create two budgets
        budget_items = json.dumps(
            [
                {
                    "name": "Item",
                    "allocated_amount": "10000",
                    "flex_class": "IMPORTANT",
                    "category": "test",
                }
            ]
        )

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
                budget_items,
                "--db",
                str(db_path),
            ],
        )
        budget1_id = result.stdout.split("budget: ")[1].split("\n")[0]

        result = runner.invoke(
            app,
            [
                "budget",
                "create",
                "--law-id",
                law_id,
                "--fiscal-year",
                "2026",
                "--items",
                budget_items,
                "--db",
                str(db_path),
            ],
        )
        budget2_id = result.stdout.split("budget: ")[1].split("\n")[0]

        # Activate first budget
        runner.invoke(app, ["budget", "activate", "--id", budget1_id, "--db", str(db_path)])

        # List all budgets
        result = runner.invoke(app, ["budget", "list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "Budgets (2):" in result.stdout
        assert budget1_id in result.stdout
        assert budget2_id in result.stdout

        # List by law
        result = runner.invoke(
            app, ["budget", "list", "--law-id", law_id, "--db", str(db_path)]
        )
        assert result.exit_code == 0
        assert "Budgets (2):" in result.stdout

        # List by status (DRAFT)
        result = runner.invoke(
            app, ["budget", "list", "--status", "DRAFT", "--db", str(db_path)]
        )
        assert result.exit_code == 0
        assert "Budgets (1):" in result.stdout
        assert budget2_id in result.stdout
        assert budget1_id not in result.stdout

        # List by status (ACTIVE)
        result = runner.invoke(
            app, ["budget", "list", "--status", "ACTIVE", "--db", str(db_path)]
        )
        assert result.exit_code == 0
        assert "Budgets (1):" in result.stdout
        assert budget1_id in result.stdout
        assert budget2_id not in result.stdout


def test_budget_show_json_output():
    """Test budget show with JSON output"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Setup
        runner.invoke(app, ["init", "--db", str(db_path)])
        result = runner.invoke(
            app, ["workspace", "create", "--name", "Test", "--db", str(db_path)]
        )
        workspace_id = result.stdout.split("workspace: ")[1].split("\n")[0]

        result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Law",
                "--reversibility",
                "SEMI_REVERSIBLE",
                "--db",
                str(db_path),
            ],
        )
        law_id = result.stdout.split("law: ")[1].split("\n")[0]

        budget_items = json.dumps(
            [
                {
                    "name": "Test Item",
                    "allocated_amount": "50000",
                    "flex_class": "IMPORTANT",
                    "category": "test",
                }
            ]
        )

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
                budget_items,
                "--db",
                str(db_path),
            ],
        )
        budget_id = result.stdout.split("budget: ")[1].split("\n")[0]

        # Get JSON output
        result = runner.invoke(
            app, ["budget", "show", "--id", budget_id, "--json", "--db", str(db_path)]
        )
        assert result.exit_code == 0

        budget_data = json.loads(result.stdout)
        assert budget_data["budget_id"] == budget_id
        assert budget_data["law_id"] == law_id
        assert budget_data["fiscal_year"] == 2025
        assert budget_data["status"] == "DRAFT"
        assert budget_data["budget_total"] == "50000"
        assert len(budget_data["items"]) == 1


def test_expenditure_with_metadata():
    """Test expenditure approval with metadata"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Setup
        runner.invoke(app, ["init", "--db", str(db_path)])
        result = runner.invoke(
            app, ["workspace", "create", "--name", "Test", "--db", str(db_path)]
        )
        workspace_id = result.stdout.split("workspace: ")[1].split("\n")[0]

        result = runner.invoke(
            app,
            [
                "law",
                "create",
                "--workspace",
                workspace_id,
                "--title",
                "Law",
                "--reversibility",
                "SEMI_REVERSIBLE",
                "--db",
                str(db_path),
            ],
        )
        law_id = result.stdout.split("law: ")[1].split("\n")[0]
        runner.invoke(app, ["law", "activate", "--id", law_id, "--db", str(db_path)])

        budget_items = json.dumps(
            [
                {
                    "name": "Item",
                    "allocated_amount": "100000",
                    "flex_class": "IMPORTANT",
                    "category": "test",
                }
            ]
        )

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
                budget_items,
                "--db",
                str(db_path),
            ],
        )
        budget_id = result.stdout.split("budget: ")[1].split("\n")[0]
        runner.invoke(app, ["budget", "activate", "--id", budget_id, "--db", str(db_path)])

        # Get item ID
        result = runner.invoke(
            app, ["budget", "show", "--id", budget_id, "--json", "--db", str(db_path)]
        )
        budget_data = json.loads(result.stdout)
        item_id = list(budget_data["items"].keys())[0]

        # Approve with metadata
        metadata = json.dumps({"vendor": "TechCorp", "po_number": "12345"})
        result = runner.invoke(
            app,
            [
                "expenditure",
                "approve",
                "--budget",
                budget_id,
                "--item",
                item_id,
                "--amount",
                "10000",
                "--purpose",
                "Server upgrade",
                "--metadata",
                metadata,
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Approved expenditure: $10000" in result.stdout
