"""
Command-line interface for AutoDev system.
"""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from core import AutoDevHarness, get_config, reset_config
from core.exceptions import AutoDevError
from core.models import Priority

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="autodev")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.pass_context
def main(ctx: click.Context, config_path: Optional[str]) -> None:
    """
    AutoDev - Autonomous Development System

    A long-running agent harness for autonomous software development.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@main.command()
@click.argument("project_path", type=click.Path())
@click.option(
    "--spec",
    "-s",
    "spec_file",
    type=click.File("r"),
    help="Path to specification file",
)
@click.option(
    "--spec-text",
    "-t",
    help="Specification as text (alternative to --spec)",
)
@click.option(
    "--run-agent",
    "-r",
    is_flag=True,
    help="Run the initializer agent (requires ANTHROPIC_API_KEY)",
)
@click.pass_context
def init(
    ctx: click.Context,
    project_path: str,
    spec_file: Optional[click.File],
    spec_text: Optional[str],
    run_agent: bool,
) -> None:
    """
    Initialize a project for AutoDev.

    Creates the .autodev directory and initial artifacts.
    Use --run-agent to have the AI generate the feature list.
    """
    config_path = ctx.obj.get("config_path")

    # Get specification
    spec = None
    if spec_file:
        spec = spec_file.read()
    elif spec_text:
        spec = spec_text

    project_path = Path(project_path).resolve()

    console.print(Panel.fit(
        f"[bold blue]AutoDev[/bold blue] - Initializing Project",
        subtitle=str(project_path),
    ))

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            spec=spec,
            config=get_config(config_path) if config_path else None,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Setting up basic structure...", total=None)

            # Basic initialization
            harness.initialize()

            progress.update(task, description="Basic structure created!")

        # Run initializer agent if requested
        if run_agent and spec:
            console.print("\n[bold]Running Initializer Agent...[/bold]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating feature list...", total=None)

                result = harness.run_initializer()

                if result.get("success"):
                    progress.update(task, description="Feature list generated!")
                else:
                    progress.update(task, description=f"Failed: {result.get('error')}")
                    console.print(f"\n[red]Agent failed:[/red] {result.get('error')}")

            if result.get("success"):
                console.print(f"\n[green]Token usage:[/green] {result.get('usage')}")
                console.print(f"[green]Tool calls:[/green] {result.get('tool_calls')}")

        # Show summary
        _show_init_summary(harness)

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option(
    "--max-iterations",
    "-m",
    type=int,
    default=100,
    help="Maximum number of iterations",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing",
)
@click.pass_context
def run(
    ctx: click.Context,
    project_path: str,
    max_iterations: int,
    dry_run: bool,
) -> None:
    """
    Run the AutoDev harness on a project.

    Continues making progress until all features are complete
    or max iterations is reached.
    """
    config_path = ctx.obj.get("config_path")
    project_path = Path(project_path).resolve()

    console.print(Panel.fit(
        f"[bold blue]AutoDev[/bold blue] - Running",
        subtitle=str(project_path),
    ))

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            config=get_config(config_path) if config_path else None,
        )

        if not harness.is_initialized():
            console.print("[red]Error:[/red] Project not initialized. Run 'autodev init' first.")
            sys.exit(1)

        # Recover and show context
        context = harness.recover_context()
        _show_context(context)

        if dry_run:
            console.print("\n[yellow]Dry run - not executing[/yellow]")
            return

        # Run the harness
        harness.run(max_iterations=max_iterations)

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command("status")
@click.argument("project_path", type=click.Path(exists=True))
@click.pass_context
def status_cmd(ctx: click.Context, project_path: str) -> None:
    """
    Show the status of an AutoDev project.
    """
    config_path = ctx.obj.get("config_path")
    project_path = Path(project_path).resolve()

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            config=get_config(config_path) if config_path else None,
        )

        if not harness.is_initialized():
            console.print("[yellow]Project not initialized with AutoDev[/yellow]")
            return

        context = harness.recover_context()
        _show_status(context, harness)

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.pass_context
def context(ctx: click.Context, project_path: str) -> None:
    """
    Show the session context for a project.

    This is what the coding agent sees at the start of each session.
    """
    config_path = ctx.obj.get("config_path")
    project_path = Path(project_path).resolve()

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            config=get_config(config_path) if config_path else None,
        )

        if not harness.is_initialized():
            console.print("[yellow]Project not initialized with AutoDev[/yellow]")
            return

        context = harness.recover_context()
        console.print(context.to_prompt_context())

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command("feature-list")
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--pending", "-p", is_flag=True, help="Show only pending features")
@click.pass_context
def feature_list_cmd(
    ctx: click.Context,
    project_path: str,
    pending: bool,
) -> None:
    """
    Show the feature list for a project.
    """
    config_path = ctx.obj.get("config_path")
    project_path = Path(project_path).resolve()

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            config=get_config(config_path) if config_path else None,
        )

        if not harness.is_initialized():
            console.print("[yellow]Project not initialized with AutoDev[/yellow]")
            return

        feature_list = harness.load_feature_list()
        _show_feature_list(feature_list, pending_only=pending)

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _show_init_summary(harness: AutoDevHarness) -> None:
    """Show summary after initialization."""
    console.print("\n[green]✓[/green] Project initialized successfully!\n")

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Project", str(harness.project_path.name))
    table.add_row("AutoDev Dir", str(harness.autodev_path.relative_to(harness.project_path)))
    table.add_row("Feature List", str(harness.feature_list_path.relative_to(harness.project_path)))
    table.add_row("Progress File", str(harness.progress_path.relative_to(harness.project_path)))

    console.print(table)

    console.print("\n[dim]Next steps:[/dim]")
    console.print("  1. Review and expand the feature list")
    console.print("  2. Run [bold]autodev run[/bold] to start development")


def _show_context(context) -> None:
    """Show session context in a nice format."""
    console.print("\n[bold]Session Context[/bold]\n")

    # Progress bar
    progress_pct = context.progress_summary.get("completion_percentage", 0)
    bar_width = 30
    filled = int(bar_width * progress_pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    console.print(f"Progress: [{bar}] {progress_pct:.1f}%")

    # Stats
    table = Table(show_header=False, box=None)
    table.add_column("Stat", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Features", str(context.progress_summary.get("total", 0)))
    table.add_row("Passing", str(context.progress_summary.get("passing", 0)))
    table.add_row("Pending", str(context.pending_features_count))
    table.add_row("In Progress", str(context.progress_summary.get("in_progress", 0)))

    console.print(table)

    # Current feature
    if context.current_feature:
        console.print(f"\n[bold]Next Feature:[/bold] {context.current_feature.id}")
        console.print(f"  {context.current_feature.description}")


def _show_status(context, harness: AutoDevHarness) -> None:
    """Show detailed project status."""
    console.print(Panel.fit(
        f"[bold]Project:[/bold] {context.project_name}",
        subtitle=f"Branch: {context.current_branch}",
    ))

    # Progress
    _show_context(context)

    # Recent commits
    if context.recent_commits:
        console.print("\n[bold]Recent Commits[/bold]")
        for commit in context.recent_commits[:5]:
            console.print(f"  [{commit['hash']}] {commit['message']}")

    # Known issues
    if context.known_issues:
        console.print("\n[yellow]Known Issues[/yellow]")
        for issue in context.known_issues:
            console.print(f"  • {issue}")

    # Environment status
    status_color = "green" if context.environment_healthy else "red"
    console.print(f"\n[{status_color}]Environment: {'Healthy' if context.environment_healthy else 'Unhealthy'}[/{status_color}]")


def _show_feature_list(feature_list, pending_only: bool = False) -> None:
    """Show feature list in a table."""
    console.print(f"\n[bold]Feature List: {feature_list.project}[/bold]\n")

    features = feature_list.get_pending_features() if pending_only else feature_list.features

    table = Table()
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Priority", width=8)
    table.add_column("Status", width=12)
    table.add_column("Description")

    for feature in features:
        status_str = "✓ Passing" if feature.passes else feature.status.value
        status_style = "green" if feature.passes else ("yellow" if feature.status.value == "in_progress" else "white")

        table.add_row(
            feature.id,
            feature.priority.value,
            f"[{status_style}]{status_str}[/{status_style}]",
            feature.description[:60] + ("..." if len(feature.description) > 60 else ""),
        )

    console.print(table)

    # Summary
    summary = feature_list.get_progress_summary()
    console.print(f"\nTotal: {summary['total']} | Passing: {summary['passing']} | Pending: {summary['pending']}")


@main.command("session")
@click.argument("project_path", type=click.Path(exists=True))
@click.pass_context
def session_cmd(ctx: click.Context, project_path: str) -> None:
    """
    Run a single coding session.

    This runs one iteration of the coder agent.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    config_path = ctx.obj.get("config_path")
    project_path = Path(project_path).resolve()

    console.print(Panel.fit(
        f"[bold blue]AutoDev[/bold blue] - Single Session",
        subtitle=str(project_path),
    ))

    try:
        harness = AutoDevHarness(
            project_path=project_path,
            config=get_config(config_path) if config_path else None,
        )

        if not harness.is_initialized():
            console.print("[red]Error:[/red] Project not initialized. Run 'autodev init' first.")
            sys.exit(1)

        # Recover context
        context = harness.recover_context()
        _show_context(context)

        if not context.current_feature:
            console.print("\n[green]All features complete![/green]")
            return

        # Run single session
        console.print(f"\n[bold]Running coding session...[/bold]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Working on feature...", total=None)

            result = harness._run_coding_session(context)

            if result.get("success"):
                progress.update(task, description="Session completed!")
            else:
                progress.update(task, description=f"Failed: {result.get('error')}")

        if result.get("success"):
            console.print(f"\n[green]Session completed successfully![/green]")
            console.print(f"[dim]Token usage: {result.get('usage')}[/dim]")
            console.print(f"[dim]Tool calls: {result.get('tool_calls')}[/dim]")
            console.print(f"[dim]Features: {result.get('features_passing')}/{result.get('features_total')} passing[/dim]")
        else:
            console.print(f"\n[red]Session failed:[/red] {result.get('error')}")

    except AutoDevError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
