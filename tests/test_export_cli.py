"""End-to-end CLI tests for incremental physical export."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from dataforge.cli.app import app
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.runtime.runner import SimulationRunner
from tests.runtime.test_simulation_runner import scenario_file

runner = CliRunner()


@pytest.mark.parametrize("export_format", ["csv", "parquet"])
def test_cli_exports_one_physical_format(tmp_path: Path, export_format: str) -> None:
    scenario = scenario_file(tmp_path / "scenario")
    output = tmp_path / export_format

    result = runner.invoke(
        app,
        [
            "simulate",
            str(scenario),
            "--format",
            export_format,
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Simulation completed" in result.output
    assert "Export completed" in result.output
    assert f"Format: {export_format}" in result.output
    extension = "csv" if export_format == "csv" else "parquet"
    assert len(tuple(output.glob(f"*.{extension}"))) == 17
    if export_format == "parquet":
        assert pq.ParquetFile(output / "metrics.parquet").metadata.num_rows == 2


def test_cli_both_runs_once_and_uses_separate_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_file(tmp_path / "scenario")
    output = tmp_path / "both"
    calls = 0
    original_run = SimulationRunner.run

    def counted_run(current: SimulationRunner):
        nonlocal calls
        calls += 1
        return original_run(current)

    monkeypatch.setattr(SimulationRunner, "run", counted_run)
    result = runner.invoke(
        app,
        ["simulate", str(scenario), "--format", "both", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert calls == 1
    assert "Formats: csv, parquet" in result.output
    assert len(tuple((output / "csv").glob("*.csv"))) == 17
    assert len(tuple((output / "parquet").glob("*.parquet"))) == 17


@pytest.mark.parametrize(
    "arguments",
    [
        ["--format", "csv"],
        ["--output", "somewhere"],
        ["--format", "invalid", "--output", "somewhere"],
    ],
)
def test_cli_rejects_invalid_export_options(
    tmp_path: Path, arguments: list[str]
) -> None:
    scenario = scenario_file(tmp_path)

    result = runner.invoke(app, ["simulate", str(scenario), *arguments])

    assert result.exit_code != 0
    assert "Simulation completed" not in result.output


def test_cli_existing_output_fails_before_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_file(tmp_path / "scenario")
    output = tmp_path / "existing"
    output.mkdir()
    (output / "transactions.csv").write_text("existing")
    called = False

    def should_not_run(current: SimulationRunner):
        nonlocal called
        called = True
        raise AssertionError("simulation must not start")

    monkeypatch.setattr(SimulationRunner, "run", should_not_run)
    result = runner.invoke(
        app,
        ["simulate", str(scenario), "--format", "csv", "--output", str(output)],
    )

    assert result.exit_code != 0
    assert not called
    assert "Simulation completed" not in result.output
    assert len(build_operational_data_model().datasets) == 17
