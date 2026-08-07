"""Developer command-line interface for DataForge Simulator."""

import shutil
import site
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated

import typer

from dataforge.runtime.runner import SimulationRunner
from dataforge.runtime.summary import build_simulation_summary

app = typer.Typer(help="Local development commands for DataForge Simulator.")

Command = Sequence[str]
Action = Callable[[], int]


class ProjectRootNotFoundError(RuntimeError):
    """Raised when the current path is outside a DataForge checkout."""


def find_project_root(start: Path | None = None) -> Path:
    """Find the closest parent directory containing pyproject.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ProjectRootNotFoundError(
        f"Could not find pyproject.toml from {current} or its parents."
    )


def find_executable(name: str) -> str | None:
    """Resolve a command, including common user-level uv locations."""
    executable = shutil.which(name)
    if executable is not None:
        return executable

    environment_candidates = (
        Path(sys.executable).parent / name,
        Path(sys.executable).parent / f"{name}.exe",
    )
    environment_executable = next(
        (str(candidate) for candidate in environment_candidates if candidate.is_file()),
        None,
    )
    if environment_executable is not None or name != "uv":
        return environment_executable

    user_base = Path(site.getuserbase())
    user_site = Path(site.getusersitepackages())
    candidates = (
        user_base / "Scripts" / "uv.exe",
        user_site.parent / "Scripts" / "uv.exe",
        user_base / "bin" / "uv",
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".local" / "bin" / "uv.exe",
    )
    return next(
        (str(candidate) for candidate in candidates if candidate.is_file()), None
    )


def run_process(arguments: Command) -> int:
    """Run a command at the repository root and return its exit code."""
    try:
        root = find_project_root()
    except ProjectRootNotFoundError as error:
        typer.echo(f"[DataForge] {error}", err=True)
        return 2

    executable_name = arguments[0]
    executable = find_executable(executable_name)
    if executable is None:
        typer.echo(f"[DataForge] Executable not found: {executable_name}", err=True)
        return 127

    resolved_arguments = [executable, *arguments[1:]]
    typer.echo(f"[DataForge] Running: {subprocess.list2cmdline(resolved_arguments)}")
    try:
        completed = subprocess.run(resolved_arguments, cwd=root, check=False)
    except KeyboardInterrupt:
        typer.echo("\n[DataForge] Command interrupted.", err=True)
        return 130
    return completed.returncode


def run_tests(arguments: Sequence[str] = ()) -> int:
    """Run Pytest with optional passthrough arguments."""
    return run_process(["pytest", *arguments])


def run_lint(*, fix: bool = False) -> int:
    """Run Ruff lint checks."""
    arguments = ["ruff", "check", "."]
    if fix:
        arguments.append("--fix")
    return run_process(arguments)


def run_format(*, write: bool = False) -> int:
    """Check or apply Ruff formatting."""
    arguments = ["ruff", "format"]
    if not write:
        arguments.append("--check")
    arguments.append(".")
    return run_process(arguments)


def run_typecheck() -> int:
    """Run static type checks."""
    return run_process(["mypy", "src"])


def run_server(host: str, port: int, *, reload: bool) -> int:
    """Run the FastAPI development server."""
    arguments = [
        "uvicorn",
        "dataforge.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        arguments.append("--reload")
    return run_process(arguments)


def run_stage(name: str, action: Action) -> int:
    """Run and report one validation stage."""
    typer.echo(f"[DataForge] Running {name}...")
    exit_code = action()
    if exit_code == 0:
        typer.echo(f"[DataForge] {name.capitalize()} passed.")
    else:
        typer.echo(
            f"[DataForge] {name.capitalize()} failed with exit code {exit_code}.",
            err=True,
        )
    return exit_code


def run_checks() -> int:
    """Run the same main quality checks used by CI, in order."""
    stages: tuple[tuple[str, Action], ...] = (
        ("format check", run_format),
        ("lint", run_lint),
        ("typecheck", run_typecheck),
        ("tests", run_tests),
    )
    for name, action in stages:
        exit_code = run_stage(name, action)
        if exit_code != 0:
            return exit_code
    return 0


def finish(exit_code: int) -> None:
    """Exit Typer only when an invoked process failed."""
    if exit_code != 0:
        raise typer.Exit(exit_code)


def _resolve_scenario_path(argument: Path) -> Path:
    """Resolve an explicit file first, then the conventional scenario directory."""
    if argument.is_file():
        return argument
    candidate = Path("configs/scenarios") / f"{argument}.yaml"
    return candidate if candidate.is_file() else argument


@app.command()
def simulate(scenario: Annotated[Path, typer.Argument(exists=False)]) -> None:
    """Execute a complete scenario through the standard simulation runtime."""
    scenario_path = _resolve_scenario_path(scenario)
    try:
        result = SimulationRunner.from_file(scenario_path).run()
        summary = build_simulation_summary(result)
    except Exception as error:
        typer.echo(f"Simulation failed: {error}", err=True)
        raise typer.Exit(1) from error

    if not summary.validation_passed:
        typer.echo("Simulation failed: final state validation is missing", err=True)
        raise typer.Exit(1)

    simulation = result.scenario.simulation
    typer.echo("Simulation completed")
    typer.echo(f"Scenario: {scenario_path.name}")
    typer.echo(f"Seed: {summary.seed}")
    typer.echo(f"Start: {simulation.start_datetime.isoformat()}")
    typer.echo(f"End: {simulation.end_datetime.isoformat()}")
    typer.echo(f"Tick unit: {summary.tick_unit}")
    typer.echo(f"Ticks processed: {summary.ticks_processed}")
    typer.echo(f"Engine executions: {summary.engine_executions}")
    typer.echo("")
    typer.echo("Run totals:")
    typer.echo(f"Demand units: {summary.demand_units}")
    typer.echo(f"Unassigned demand units: {summary.unassigned_demand_units}")
    typer.echo(f"Total transactions: {summary.total_transactions}")
    typer.echo(f"Completed transactions: {summary.completed_transactions}")
    typer.echo(
        f"Partially completed transactions: {summary.partially_completed_transactions}"
    )
    typer.echo(f"Rejected transactions: {summary.rejected_transactions}")
    typer.echo(f"Completed lines: {summary.completed_lines}")
    typer.echo(f"Rejected lines: {summary.rejected_lines}")
    typer.echo(f"Completed units: {summary.completed_units}")
    typer.echo(f"Rejected units: {summary.rejected_units}")
    typer.echo(f"Net sales: {summary.net_sales_amount}")
    typer.echo(f"Lost sales: {summary.lost_sales_amount}")
    typer.echo(f"Out-of-stock events/signals: {summary.out_of_stock_signals}")
    typer.echo(f"Replenishments completed: {summary.replenishments_completed}")
    typer.echo(f"Units replenished: {summary.units_replenished}")


@app.command()
def setup() -> None:
    """Synchronize the development environment and dependencies."""
    typer.echo("[DataForge] Synchronizing development dependencies...")
    finish(run_process(["uv", "sync", "--dev"]))


@app.command()
def run(
    host: str = typer.Option("127.0.0.1", help="Address on which to bind."),
    port: int = typer.Option(8000, min=1, max=65535, help="Port on which to bind."),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Start the FastAPI development server."""
    finish(run_server(host, port, reload=reload))


@app.command(
    name="test",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test_command(context: typer.Context) -> None:
    """Run tests, forwarding arguments after -- to Pytest."""
    finish(run_tests(context.args))


@app.command()
def lint(fix: bool = typer.Option(False, "--fix", help="Apply safe fixes.")) -> None:
    """Run Ruff lint checks."""
    finish(run_lint(fix=fix))


@app.command(name="format")
def format_command(
    write: bool = typer.Option(False, "--write", help="Apply formatting changes."),
) -> None:
    """Check formatting, or apply it with --write."""
    finish(run_format(write=write))


@app.command()
def typecheck() -> None:
    """Run mypy over application source code."""
    finish(run_typecheck())


@app.command()
def check() -> None:
    """Run the main CI quality checks locally."""
    finish(run_checks())


@app.command()
def dev(
    test: bool = typer.Option(False, "--test", help="Run tests before starting."),
    check: bool = typer.Option(
        False, "--check", help="Run all checks before starting."
    ),
    host: str = typer.Option("127.0.0.1", help="Address on which to bind."),
    port: int = typer.Option(8000, min=1, max=65535, help="Port on which to bind."),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Optionally validate, then start the development server."""
    if test and check:
        raise typer.BadParameter("--test and --check cannot be used together")

    if test:
        finish(run_stage("tests", run_tests))
    elif check:
        finish(run_checks())

    finish(run_server(host, port, reload=reload))
