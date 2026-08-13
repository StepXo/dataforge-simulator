"""Small Simulation-to-DuckDB-to-business-SQL integration test."""

from decimal import Decimal
from pathlib import Path

import duckdb

from dataforge.analytics.business import BusinessQuery, run_business_query
from dataforge.export.analytical import (
    DuckDBAnalyticalSink,
    DuckDBOperationalAnalyticsSink,
)
from dataforge.runtime.runner import SimulationRunner


def test_smoke_simulation_revenue_is_queryable_by_location(tmp_path: Path) -> None:
    database = tmp_path / "business.duckdb"
    result = SimulationRunner.from_file(
        Path("configs/scenarios/smoke-test.yaml"),
        sink=DuckDBOperationalAnalyticsSink(DuckDBAnalyticalSink(database)),
    ).run()
    connection = duckdb.connect(str(database), read_only=True)
    try:
        rows = run_business_query(connection, BusinessQuery.REVENUE_BY_LOCATION)
    finally:
        connection.close()

    net_sales: list[Decimal] = []
    for row in rows:
        value = row["net_sales"]
        assert isinstance(value, Decimal)
        net_sales.append(value)
    assert sum(net_sales, start=Decimal("0.00")) == (
        result.metrics_summary.net_sales_amount
    )
