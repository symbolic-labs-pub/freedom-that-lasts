"""
Freedom That Lasts CLI

Command-line interface for the FTL governance system.
Provides commands for workspace management, delegations, laws, and monitoring.

Usage:
    ftl init --db governance.db
    ftl workspace create --name "Health Services"
    ftl delegate create --from alice --to bob --workspace <id> --ttl-days 180
    ftl law create --workspace <id> --title "Primary Care Pilot" ...
    ftl law activate --id <law_id>
    ftl tick
    ftl health
"""

import json
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from freedom_that_lasts.ftl import FTL

app = typer.Typer(
    name="ftl",
    help="Freedom That Lasts - Anti-tyranny governance system",
    add_completion=False,
)

# Sub-apps
workspace_app = typer.Typer(help="Workspace management commands")
delegate_app = typer.Typer(help="Delegation management commands")
law_app = typer.Typer(help="Law lifecycle management commands")

app.add_typer(workspace_app, name="workspace")
app.add_typer(delegate_app, name="delegate")
app.add_typer(law_app, name="law")

# Global state
DEFAULT_DB = Path(".ftl.db")


def get_ftl(db_path: Optional[Path] = None) -> FTL:
    """Get FTL instance"""
    db = db_path or DEFAULT_DB
    if not db.exists():
        typer.echo(f"Error: Database not found: {db}", err=True)
        typer.echo(f"Run 'ftl init --db {db}' to initialize", err=True)
        raise typer.Exit(1)
    return FTL(str(db))


# Initialization command


@app.command()
def init(
    db: Annotated[
        Path,
        typer.Option(help="Database path"),
    ] = DEFAULT_DB,
) -> None:
    """Initialize a new FTL database"""
    if db.exists():
        typer.echo(f"Error: Database already exists: {db}", err=True)
        raise typer.Exit(1)

    # Create database by initializing FTL
    FTL(str(db))
    typer.echo(f"✓ Initialized FTL database: {db}")


# Workspace commands


@workspace_app.command("create")
def workspace_create(
    name: Annotated[str, typer.Option("--name", help="Workspace name")],
    scope: Annotated[
        Optional[str],
        typer.Option("--scope", help="Workspace scope (JSON)"),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Create a new workspace"""
    ftl = get_ftl(db)

    scope_dict = json.loads(scope) if scope else {}
    workspace = ftl.create_workspace(name=name, scope=scope_dict)

    typer.echo(f"✓ Created workspace: {workspace['workspace_id']}")
    typer.echo(f"  Name: {workspace['name']}")
    if workspace.get("scope"):
        typer.echo(f"  Scope: {json.dumps(workspace['scope'])}")


@workspace_app.command("list")
def workspace_list(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """List all active workspaces"""
    ftl = get_ftl(db)
    workspaces = ftl.list_workspaces()

    if not workspaces:
        typer.echo("No active workspaces")
        return

    typer.echo(f"Active Workspaces ({len(workspaces)}):")
    for ws in workspaces:
        typer.echo(f"  {ws['workspace_id']}: {ws['name']}")


# Delegation commands


@delegate_app.command("create")
def delegate_create(
    from_actor: Annotated[str, typer.Option("--from", help="Delegating actor")],
    to: Annotated[str, typer.Option("--to", help="Receiving actor")],
    workspace: Annotated[str, typer.Option("--workspace", help="Workspace ID")],
    ttl_days: Annotated[int, typer.Option("--ttl-days", help="Time-to-live in days")],
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Delegate decision rights"""
    ftl = get_ftl(db)

    delegation = ftl.delegate(
        from_actor=from_actor,
        workspace_id=workspace,
        to_actor=to,
        ttl_days=ttl_days,
    )

    typer.echo(f"✓ Created delegation: {delegation['delegation_id']}")
    typer.echo(f"  From: {delegation['from_actor']}")
    typer.echo(f"  To: {delegation['to_actor']}")
    typer.echo(f"  TTL: {delegation['ttl_days']} days")
    typer.echo(f"  Expires: {delegation['expires_at']}")


# Law commands


@law_app.command("create")
def law_create(
    workspace: Annotated[str, typer.Option("--workspace", help="Workspace ID")],
    title: Annotated[str, typer.Option("--title", help="Law title")],
    reversibility: Annotated[
        str,
        typer.Option(
            "--reversibility",
            help="Reversibility class (REVERSIBLE, SEMI_REVERSIBLE, IRREVERSIBLE)",
        ),
    ],
    checkpoints: Annotated[
        str,
        typer.Option("--checkpoints", help="Checkpoint schedule (comma-separated days)"),
    ] = "30,90,180,365",
    scope: Annotated[
        Optional[str],
        typer.Option("--scope", help="Law scope (JSON)"),
    ] = None,
    params: Annotated[
        Optional[str],
        typer.Option("--params", help="Law parameters (JSON)"),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Create a new law"""
    ftl = get_ftl(db)

    checkpoint_list = [int(d.strip()) for d in checkpoints.split(",")]
    scope_dict = json.loads(scope) if scope else {}
    params_dict = json.loads(params) if params else {}

    law = ftl.create_law(
        workspace_id=workspace,
        title=title,
        scope=scope_dict,
        reversibility_class=reversibility,
        checkpoints=checkpoint_list,
        params=params_dict,
    )

    typer.echo(f"✓ Created law: {law['law_id']}")
    typer.echo(f"  Title: {law['title']}")
    typer.echo(f"  Status: {law['status']}")
    typer.echo(f"  Reversibility: {law['reversibility_class']}")
    typer.echo(f"  Checkpoints: {law['checkpoints']}")


@law_app.command("activate")
def law_activate(
    law_id: Annotated[str, typer.Option("--id", help="Law ID")],
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Activate a law (DRAFT → ACTIVE)"""
    ftl = get_ftl(db)

    law = ftl.activate_law(law_id=law_id)

    typer.echo(f"✓ Activated law: {law['law_id']}")
    typer.echo(f"  Title: {law['title']}")
    typer.echo(f"  Status: {law['status']}")
    typer.echo(f"  Next checkpoint: {law.get('next_checkpoint_at')}")


@law_app.command("list")
def law_list(
    status: Annotated[
        Optional[str],
        typer.Option("--status", help="Filter by status (DRAFT, ACTIVE, REVIEW, etc.)"),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """List laws"""
    ftl = get_ftl(db)

    laws = ftl.list_laws(status=status)

    if not laws:
        typer.echo(f"No laws{f' with status {status}' if status else ''}")
        return

    typer.echo(f"Laws ({len(laws)}):")
    for law in laws:
        typer.echo(
            f"  {law['law_id']}: {law['title']} [{law['status']}]"
        )


@law_app.command("review")
def law_review(
    law_id: Annotated[str, typer.Option("--id", help="Law ID")],
    outcome: Annotated[
        str,
        typer.Option("--outcome", help="Review outcome (continue, adjust, sunset)"),
    ],
    notes: Annotated[str, typer.Option("--notes", help="Review notes")],
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Complete a law review"""
    ftl = get_ftl(db)

    law = ftl.complete_review(law_id=law_id, outcome=outcome, notes=notes)

    typer.echo(f"✓ Completed review for law: {law['law_id']}")
    typer.echo(f"  Title: {law['title']}")
    typer.echo(f"  Outcome: {outcome}")
    typer.echo(f"  New status: {law['status']}")


# Monitoring commands


@app.command()
def tick(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Run trigger evaluation loop"""
    ftl = get_ftl(db)

    result = ftl.tick()

    typer.echo(f"✓ Tick completed: {result.tick_id}")
    typer.echo(f"  Risk level: {result.freedom_health.risk_level.value}")
    typer.echo(f"  Events triggered: {len(result.triggered_events)}")

    if result.has_warnings():
        typer.echo("  ⚠️  Warnings detected!")
    if result.has_halts():
        typer.echo("  🛑 HALT conditions detected!")

    # Show triggered events
    if result.triggered_events:
        typer.echo("\n  Triggered events:")
        for event in result.triggered_events:
            typer.echo(f"    - {event.event_type}")


@app.command()
def health(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show system health status"""
    ftl = get_ftl(db)

    health_score = ftl.health()

    if json_output:
        typer.echo(json.dumps(health_score.model_dump(), indent=2, default=str))
        return

    # Pretty print
    risk_emoji = {
        "GREEN": "✓",
        "YELLOW": "⚠️",
        "RED": "🛑",
    }
    emoji = risk_emoji.get(health_score.risk_level.value, "?")

    typer.echo(f"\nFreedom Health Status: {emoji} {health_score.risk_level.value}")
    typer.echo("\nDelegation Concentration:")
    typer.echo(f"  Gini Coefficient: {health_score.concentration.gini_coefficient:.3f}")
    typer.echo(f"  Max In-Degree: {health_score.concentration.max_in_degree}")
    typer.echo(f"  Total Active Delegations: {health_score.concentration.total_active_delegations}")
    typer.echo(f"  Unique Delegates: {health_score.concentration.unique_delegates}")

    typer.echo("\nLaw Review Health:")
    typer.echo(f"  Total Active Laws: {health_score.law_review_health.total_active_laws}")
    typer.echo(f"  Overdue Reviews: {health_score.law_review_health.overdue_reviews}")
    typer.echo(f"  Upcoming (7d): {health_score.law_review_health.upcoming_reviews_7d}")
    typer.echo(f"  Upcoming (30d): {health_score.law_review_health.upcoming_reviews_30d}")

    if health_score.reasons and health_score.reasons != ["All safeguards within normal bounds"]:
        typer.echo("\nRisk Factors:")
        for reason in health_score.reasons:
            typer.echo(f"  - {reason}")


@app.command()
def safety(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """Show safety policy and recent events"""
    ftl = get_ftl(db)

    policy = ftl.get_safety_policy()
    recent_events = ftl.get_safety_events(limit=10)

    typer.echo("Safety Policy:")
    typer.echo(f"  Delegation Gini Warning: {policy.delegation_gini_warn}")
    typer.echo(f"  Delegation Gini Halt: {policy.delegation_gini_halt}")
    typer.echo(f"  Delegation In-Degree Warning: {policy.delegation_in_degree_warn}")
    typer.echo(f"  Delegation In-Degree Halt: {policy.delegation_in_degree_halt}")
    typer.echo(f"  Max Delegation TTL: {policy.max_delegation_ttl_days} days")

    if recent_events:
        typer.echo(f"\nRecent Safety Events ({len(recent_events)}):")
        for event in recent_events:
            typer.echo(f"  {event['occurred_at']}: {event['event_type']}")
    else:
        typer.echo("\nNo safety events logged")


def main() -> None:
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
