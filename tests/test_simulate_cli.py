"""Tests for the public simulation CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from dataforge.cli import app
from tests.runtime.test_simulation_runner import scenario_file

runner = CliRunner()


def test_simulate_runs_complete_small_scenario(tmp_path: Path) -> None:
    path = scenario_file(tmp_path)

    result = runner.invoke(app, ["simulate", str(path)])

    assert result.exit_code == 0
    assert "Simulation completed" in result.output
    assert "Seed: 42" in result.output
    assert "Ticks processed: 2" in result.output
    assert "Engine executions: 20" in result.output
    assert "Completed transactions:" in result.output
    assert "Net sales:" in result.output


def test_simulate_missing_scenario_fails_without_success(tmp_path: Path) -> None:
    result = runner.invoke(app, ["simulate", str(tmp_path / "missing.yaml")])

    assert result.exit_code != 0
    assert "Simulation failed:" in result.output
    assert "Simulation completed" not in result.output
