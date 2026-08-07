"""Tests for accumulation of official per-tick runtime metrics."""

from datetime import datetime
from decimal import Decimal

from dataforge.engines.metrics.models import MetricsContext
from dataforge.runtime.summary import aggregate_run_metrics
from dataforge.state.simulation_state import SimulationState


def metrics(tick: int, value: int) -> MetricsContext:
    money = Decimal(value)
    return MetricsContext(
        tick_index=tick,
        current_time=datetime(2026, 8, 10, tick),
        demand_records=value,
        demand_units=value,
        purchase_intents=value,
        intent_units=value,
        unassigned_demand_units=value,
        price_quotes=value,
        total_transactions=value,
        completed_transactions=value,
        partially_completed_transactions=value,
        rejected_transactions=value,
        transaction_lines=value,
        completed_lines=value,
        rejected_lines=value,
        completed_units=value,
        rejected_units=value,
        gross_sales_amount=money,
        discount_amount=money,
        net_sales_amount=money,
        lost_sales_amount=money,
        inventory_movements=value,
        units_removed_from_inventory=value,
        reorder_signals=value,
        out_of_stock_signals=value,
        replenishments_scheduled=value,
        replenishments_completed=value,
        units_replenished=value,
    )


def test_run_metrics_summary_sums_all_ticks_not_only_final_tick() -> None:
    state = SimulationState()
    collection = state.create_collection("metrics_context")
    for tick, value in enumerate((10, 20, 30)):
        collection.add(f"tick-{tick}", metrics(tick, value))

    summary = aggregate_run_metrics(state, 3)

    assert summary.ticks_aggregated == 3
    assert summary.completed_transactions == 60
    assert summary.rejected_transactions == 60
    assert summary.demand_units == 60
    assert summary.replenishments_completed == 60
    assert summary.net_sales_amount == Decimal("60")
    assert summary.lost_sales_amount == Decimal("60")
