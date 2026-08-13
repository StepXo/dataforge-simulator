"""Physical exporter integration with the incremental simulation runtime."""

import csv
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from dataforge.export.files.configuration import ExportFormat, build_export_sink
from dataforge.export.files.csv_sink import CsvOperationalDataSink
from dataforge.export.files.parquet_sink import ParquetOperationalDataSink
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.export.operational.sink import NullOperationalDataSink
from dataforge.runtime.result import SimulationResult
from dataforge.runtime.runner import SimulationRunner
from tests.runtime.test_simulation_runner import TICK_COLLECTIONS

SCENARIO = Path("configs/scenarios/smoke-test.yaml")


def inventory_snapshot(result: SimulationResult) -> tuple[object, ...]:
    return result.state.collection("inventory").all()


def csv_counts(directory: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dataset in build_operational_data_model().datasets:
        with (directory / f"{dataset.name}.csv").open(
            encoding="utf-8", newline=""
        ) as file:
            counts[dataset.name] = max(sum(1 for _ in csv.reader(file)) - 1, 0)
    return counts


def parquet_counts(directory: Path) -> dict[str, int]:
    return {
        dataset.name: pq.ParquetFile(
            directory / f"{dataset.name}.parquet"
        ).metadata.num_rows
        for dataset in build_operational_data_model().datasets
    }


def test_smoke_scenario_is_equivalent_across_all_incremental_sinks(
    tmp_path: Path,
) -> None:
    csv_directory = tmp_path / "csv"
    parquet_directory = tmp_path / "parquet"
    both_directory = tmp_path / "both"

    null_result = SimulationRunner.from_file(
        SCENARIO, sink=NullOperationalDataSink()
    ).run()
    csv_result = SimulationRunner.from_file(
        SCENARIO, sink=CsvOperationalDataSink(csv_directory, batch_size=7)
    ).run()
    both_result = SimulationRunner.from_file(
        SCENARIO, sink=build_export_sink(ExportFormat.BOTH, both_directory)
    ).run()
    parquet_result = SimulationRunner.from_file(
        SCENARIO,
        sink=ParquetOperationalDataSink(parquet_directory, batch_size=7),
    ).run()

    assert null_result.metrics_summary == csv_result.metrics_summary
    assert null_result.metrics_summary == parquet_result.metrics_summary
    assert null_result.metrics_summary == both_result.metrics_summary
    assert inventory_snapshot(null_result) == inventory_snapshot(csv_result)
    assert inventory_snapshot(null_result) == inventory_snapshot(parquet_result)
    assert inventory_snapshot(null_result) == inventory_snapshot(both_result)
    assert csv_counts(csv_directory) == parquet_counts(parquet_directory)
    assert csv_counts(both_directory / "csv") == parquet_counts(
        both_directory / "parquet"
    )
    assert csv_counts(csv_directory)["metrics"] == 24
    with (csv_directory / "transaction_lines.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        lines = tuple(csv.DictReader(file))
    assert all(
        Decimal(line["gross_amount"])
        == Decimal(line["unit_price"]) * int(line["quantity"])
        and Decimal(line["net_amount"])
        == Decimal(line["gross_amount"]) - Decimal(line["discount_amount"])
        for line in lines
    )

    with (csv_directory / "transactions.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        transactions = tuple(csv.DictReader(file))
    start = datetime(2024, 1, 1)
    transaction_times = {
        item["transaction_id"]: datetime.fromisoformat(item["occurred_at"])
        for item in transactions
    }
    assert all(
        start + timedelta(hours=int(item["tick_index"]))
        <= transaction_times[item["transaction_id"]]
        < start + timedelta(hours=int(item["tick_index"]) + 1)
        for item in transactions
    )
    assert any(
        transaction_times[item["transaction_id"]]
        != start + timedelta(hours=int(item["tick_index"]))
        for item in transactions
    )

    with (csv_directory / "inventory_movements.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        movements = tuple(csv.DictReader(file))
    assert all(
        datetime.fromisoformat(item["occurred_at"])
        == transaction_times[item["transaction_id"]]
        for item in movements
        if item["movement_type"] == "sale"
    )
    replenishment_movements = {
        item["replenishment_id"]: item
        for item in movements
        if item["movement_type"] == "replenishment"
    }
    with (csv_directory / "replenishments.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        replenishments = tuple(csv.DictReader(file))
    for item in replenishments:
        if item["status"] == "pending":
            assert item["completed_tick_index"] == ""
            assert item["completed_at"] == ""
            assert item["received_quantity"] == ""
            continue
        assert item["completed_tick_index"] != ""
        assert item["completed_at"] != ""
        assert item["received_quantity"] != ""
        if int(item["received_quantity"]) > 0:
            assert item["replenishment_id"] in replenishment_movements
    parquet_replenishments = pq.read_table(
        parquet_directory / "replenishments.parquet"
    ).to_pylist()
    assert {
        (
            item["replenishment_id"],
            item["status"],
            item["completed_tick_index"],
            item["received_quantity"],
        )
        for item in parquet_replenishments
    } == {
        (
            item["replenishment_id"],
            item["status"],
            int(item["completed_tick_index"]) if item["completed_tick_index"] else None,
            int(item["received_quantity"]) if item["received_quantity"] else None,
        )
        for item in replenishments
    }
    for result in (null_result, csv_result, parquet_result, both_result):
        assert all(
            result.state.collection(name).count() == 0 for name in TICK_COLLECTIONS
        )
