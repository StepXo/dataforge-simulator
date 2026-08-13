"""Direct Simulation-to-AnalyticalRecord-to-DuckDB integration."""

from decimal import Decimal
from pathlib import Path

import duckdb

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
