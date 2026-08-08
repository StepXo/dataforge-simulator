"""Integration tests for server-side CSV and Parquet exports."""

import csv
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from dataforge.api.app import app
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.runtime.runner import SimulationRunner
from tests.runtime.test_simulation_runner import scenario_file

client = TestClient(app)


def _csv_counts(directory: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dataset in build_operational_data_model().datasets:
        with (directory / f"{dataset.name}.csv").open(
            encoding="utf-8", newline=""
        ) as file:
            counts[dataset.name] = max(sum(1 for _ in csv.reader(file)) - 1, 0)
    return counts


def _parquet_counts(directory: Path) -> dict[str, int]:
    return {
        dataset.name: pq.ParquetFile(
            directory / f"{dataset.name}.parquet"
        ).metadata.num_rows
        for dataset in build_operational_data_model().datasets
    }


@pytest.mark.parametrize("export_format", ["csv", "parquet"])
def test_api_exports_individual_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, export_format: str
) -> None:
    scenario = scenario_file(tmp_path / "scenario").resolve()
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/simulation/export",
        json={
            "scenario": str(scenario),
            "format": export_format,
            "output": export_format,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == export_format
    assert body["datasets"] == 17
    assert body["ticks_processed"] == 2
    assert body["validation_passed"] is True
    extension = "csv" if export_format == "csv" else "parquet"
    assert (
        len(tuple((tmp_path / "outputs" / export_format).glob(f"*.{extension}"))) == 17
    )


def test_api_both_runs_once_and_has_equal_logical_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_file(tmp_path / "scenario").resolve()
    monkeypatch.chdir(tmp_path)
    calls = 0
    original_run = SimulationRunner.run

    def counted_run(current: SimulationRunner):
        nonlocal calls
        calls += 1
        return original_run(current)

    monkeypatch.setattr(SimulationRunner, "run", counted_run)
    response = client.post(
        "/simulation/export",
        json={"scenario": str(scenario), "format": "both", "output": "combined"},
    )

    assert response.status_code == 200, response.text
    assert calls == 1
    root = tmp_path / "outputs/combined"
    assert _csv_counts(root / "csv") == _parquet_counts(root / "parquet")


def test_api_existing_output_returns_conflict_before_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_file(tmp_path / "scenario").resolve()
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "outputs/combined/csv"
    existing.mkdir(parents=True)
    (existing / "transactions.csv").write_text("existing")
    called = False

    def should_not_run(current: SimulationRunner):
        nonlocal called
        called = True
        raise AssertionError("simulation must not start")

    monkeypatch.setattr(SimulationRunner, "run", should_not_run)
    response = client.post(
        "/simulation/export",
        json={"scenario": str(scenario), "format": "both", "output": "combined"},
    )

    assert response.status_code == 409
    assert not called


@pytest.mark.parametrize(
    "payload",
    [
        {"scenario": "smoke-test", "format": "invalid", "output": "demo"},
        {"scenario": "smoke-test", "format": "csv"},
        {"scenario": "smoke-test", "output": "demo"},
    ],
)
def test_api_rejects_invalid_export_request(payload: dict[str, str]) -> None:
    response = client.post("/simulation/export", json=payload)

    assert response.status_code == 422


def test_api_rejects_path_traversal_without_creating_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_file(tmp_path / "scenario").resolve()
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "outside"

    response = client.post(
        "/simulation/export",
        json={
            "scenario": str(scenario),
            "format": "csv",
            "output": "../../outside",
        },
    )

    assert response.status_code == 422
    assert not outside.exists()
