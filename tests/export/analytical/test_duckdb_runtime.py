"""Direct Simulation-to-AnalyticalRecord-to-DuckDB integration."""

from decimal import Decimal
from pathlib import Path

import duckdb
import yaml

from dataforge.export.analytical import (
    DuckDBAnalyticalSink,
    DuckDBOperationalAnalyticsSink,
)
from dataforge.runtime.runner import SimulationRunner
from tests.runtime.test_simulation_runner import TICK_COLLECTIONS

SCENARIO = Path("configs/scenarios/smoke-test.yaml")


def test_simulation_streams_analytical_batches_directly_to_duckdb(
    tmp_path: Path,
) -> None:
    path = tmp_path / "simulation.duckdb"
    result = SimulationRunner.from_file(
        SCENARIO,
        sink=DuckDBOperationalAnalyticsSink(DuckDBAnalyticalSink(path)),
    ).run()

    connection = duckdb.connect(str(path), read_only=True)
    try:
        count_row = connection.execute("SELECT count(*) FROM fact_sales").fetchone()
        net_row = connection.execute(
            "SELECT coalesce(sum(net_sales_amount), 0) FROM fact_sales"
        ).fetchone()
        lost_row = connection.execute(
            "SELECT coalesce(sum(lost_sales_amount), 0) FROM fact_sales"
        ).fetchone()
    finally:
        connection.close()

    assert count_row is not None and net_row is not None and lost_row is not None
    fact_count = count_row[0]
    net_sales = net_row[0]
    lost_sales = lost_row[0]
    assert fact_count == result.metrics_summary.transaction_lines
    assert Decimal(str(net_sales)) == result.metrics_summary.net_sales_amount
    assert Decimal(str(lost_sales)) == result.metrics_summary.lost_sales_amount
    assert all(result.state.collection(name).count() == 0 for name in TICK_COLLECTIONS)


def test_incremental_inventory_movement_facts_have_unique_ids_across_engines(
    tmp_path: Path,
) -> None:
    content = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    content["simulation"]["end_datetime"] = "2024-01-04T00:00:00"
    content["geography"]["source"] = str(
        Path("configs/geography/colombia.yaml").resolve()
    )
    content["products"]["source"] = str(
        Path("configs/products/taqueria.yaml").resolve()
    )
    content["replenishment"] = {
        "min_lead_time_days": 1,
        "max_lead_time_days": 1,
    }
    content["customers"] = {
        "count": 50,
        "inactive_probability": 0,
        "activity_profiles": [
            {
                "name": "active",
                "weight": 1,
                "monthly_rate_mean": 100,
                "variation": 0,
                "segment": "regular",
            }
        ],
    }
    content["inventory"] = {
        "min_initial_stock": 2,
        "max_initial_stock": 2,
        "min_reorder_point": 1,
        "max_reorder_point": 1,
        "max_stock_multiplier": 5,
        "product_availability_probability": 1,
    }
    content["demand"]["base_demand_min"] = 2
    content["demand"]["base_demand_max"] = 3
    scenario = tmp_path / "overlapping-movements.yaml"
    scenario.write_text(yaml.safe_dump(content), encoding="utf-8")
    database = tmp_path / "overlapping-movements.duckdb"

    SimulationRunner.from_file(
        scenario,
        sink=DuckDBOperationalAnalyticsSink(DuckDBAnalyticalSink(database)),
    ).run()

    connection = duckdb.connect(str(database), read_only=True)
    try:
        counts = connection.execute(
            "SELECT count(*), count(DISTINCT movement_id) FROM fact_inventory_movement"
        ).fetchone()
        overlap = connection.execute(
            "SELECT count(*) FROM ("
            "SELECT tick_index FROM fact_inventory_movement "
            "GROUP BY tick_index "
            "HAVING count(DISTINCT movement_type) = 2"
            ")"
        ).fetchone()
    finally:
        connection.close()

    assert counts is not None
    total, unique = counts
    assert total == unique
    assert overlap is not None and overlap[0] > 0
