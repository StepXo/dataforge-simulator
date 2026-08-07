"""Tests for the public simulation CLI command."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from dataforge.cli import app
from dataforge.scenario import load_scenario
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
    assert "Run totals:" in result.output
    assert "Total transactions:" in result.output
    assert "Completed transactions:" in result.output
    assert "Partially completed transactions:" in result.output
    assert "Net sales:" in result.output


def test_simulate_missing_scenario_fails_without_success(tmp_path: Path) -> None:
    result = runner.invoke(app, ["simulate", str(tmp_path / "missing.yaml")])

    assert result.exit_code != 0
    assert "Simulation failed:" in result.output
    assert "Simulation completed" not in result.output


def test_simulate_resolves_scenario_name_from_default_directory(
    tmp_path: Path, monkeypatch
) -> None:
    original = scenario_file(tmp_path / "source")
    payload = yaml.safe_load(original.read_text(encoding="utf-8"))
    loaded = load_scenario(original)
    payload["geography"]["source"] = str(loaded.geography.source)
    payload["products"]["source"] = str(loaded.products.source)
    scenarios = tmp_path / "configs/scenarios"
    scenarios.mkdir(parents=True)
    target = scenarios / "named.yaml"
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["simulate", "named"])

    assert result.exit_code == 0
    assert "Scenario: named.yaml" in result.output
    assert "Run totals:" in result.output
