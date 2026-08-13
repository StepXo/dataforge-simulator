"""Analytical transformation integration over retained operational history."""

from decimal import Decimal
from pathlib import Path

from dataforge.analytics import AnalyticalDataBuilder
from dataforge.export.operational import OperationalDataBuilder
from dataforge.runtime.runner import SimulationRunner

SCENARIO = Path("configs/scenarios/smoke-test.yaml")


def test_full_and_incremental_operational_phases_produce_same_analytical_rows() -> None:
    result = SimulationRunner.from_file(SCENARIO).run()
    operational = OperationalDataBuilder()
    operational_rows = tuple(operational.iter_result_rows(result))

    full = tuple(AnalyticalDataBuilder().transform(operational_rows))

    incremental_builder = AnalyticalDataBuilder()
    incremental = list(
        incremental_builder.transform(operational.iter_master_rows(result.state))
    )
    for tick_index in range(result.simulation_summary.ticks_processed):
        incremental.extend(
            incremental_builder.transform(
                operational.iter_tick_rows(result.state, tick_index)
            )
        )
    incremental.extend(
        incremental_builder.transform(operational.iter_final_rows(result.state))
    )

    assert tuple(incremental) == full
    names = {record.dataset for record in full}
    assert {
        "dim_date",
        "dim_customer",
        "dim_product",
        "dim_location",
        "dim_promotion",
        "fact_sales",
        "fact_inventory_movement",
    } <= names

    sales = tuple(record for record in full if record.dataset == "fact_sales")
    movements = tuple(
        record for record in full if record.dataset == "fact_inventory_movement"
    )
    assert (
        sum(
            (record.values["net_sales_amount"] for record in sales),
            start=Decimal("0.00"),
        )
        == result.metrics_summary.net_sales_amount
    )
    assert (
        sum(
            (record.values["lost_sales_amount"] for record in sales),
            start=Decimal("0.00"),
        )
        == result.metrics_summary.lost_sales_amount
    )
    assert len(movements) == sum(
        record.dataset == "inventory_movements" for record in operational_rows
    )
