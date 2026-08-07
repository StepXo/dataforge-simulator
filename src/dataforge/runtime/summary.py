"""Shared read-only summary extraction for public runtime surfaces."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from dataforge.core.state.simulation_state import SimulationState
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.validation.models import ValidationContext
from dataforge.runtime.result import RunMetricsSummary, SimulationResult


@dataclass(frozen=True, slots=True)
class SimulationRuntimeSummary:
    """Compact official totals from one completed simulation result."""

    seed: int
    start_datetime: datetime
    end_datetime: datetime
    tick_unit: str
    ticks_processed: int
    engine_executions: int
    validation_passed: bool
    demand_units: int
    unassigned_demand_units: int
    total_transactions: int
    completed_transactions: int
    partially_completed_transactions: int
    rejected_transactions: int
    transaction_lines: int
    completed_lines: int
    rejected_lines: int
    completed_units: int
    rejected_units: int
    net_sales_amount: Decimal
    lost_sales_amount: Decimal
    out_of_stock_signals: int
    replenishments_completed: int
    units_replenished: int


def aggregate_run_metrics(
    state: SimulationState,
    ticks_processed: int,
) -> RunMetricsSummary:
    """Sum every official per-tick metrics snapshot in tick order."""
    if not state.has_collection("metrics_context"):
        raise ValueError("Required runtime collection is missing: metrics_context")
    collection = state.collection("metrics_context")
    metrics: list[MetricsContext] = []
    for tick_index in range(ticks_processed):
        value = collection.get(f"tick-{tick_index}")
        if not isinstance(value, MetricsContext):
            raise ValueError(f"MetricsContext is missing for tick: {tick_index}")
        metrics.append(value)
    zero = Decimal("0.00")
    return RunMetricsSummary(
        ticks_aggregated=len(metrics),
        demand_records=sum(item.demand_records for item in metrics),
        demand_units=sum(item.demand_units for item in metrics),
        purchase_intents=sum(item.purchase_intents for item in metrics),
        intent_units=sum(item.intent_units for item in metrics),
        unassigned_demand_units=sum(item.unassigned_demand_units for item in metrics),
        price_quotes=sum(item.price_quotes for item in metrics),
        total_transactions=sum(item.total_transactions for item in metrics),
        completed_transactions=sum(item.completed_transactions for item in metrics),
        partially_completed_transactions=sum(
            item.partially_completed_transactions for item in metrics
        ),
        rejected_transactions=sum(item.rejected_transactions for item in metrics),
        transaction_lines=sum(item.transaction_lines for item in metrics),
        completed_lines=sum(item.completed_lines for item in metrics),
        rejected_lines=sum(item.rejected_lines for item in metrics),
        completed_units=sum(item.completed_units for item in metrics),
        rejected_units=sum(item.rejected_units for item in metrics),
        gross_sales_amount=sum((item.gross_sales_amount for item in metrics), zero),
        discount_amount=sum((item.discount_amount for item in metrics), zero),
        net_sales_amount=sum((item.net_sales_amount for item in metrics), zero),
        lost_sales_amount=sum((item.lost_sales_amount for item in metrics), zero),
        inventory_movements=sum(item.inventory_movements for item in metrics),
        units_removed_from_inventory=sum(
            item.units_removed_from_inventory for item in metrics
        ),
        reorder_signals=sum(item.reorder_signals for item in metrics),
        out_of_stock_signals=sum(item.out_of_stock_signals for item in metrics),
        replenishments_scheduled=sum(item.replenishments_scheduled for item in metrics),
        replenishments_completed=sum(item.replenishments_completed for item in metrics),
        units_replenished=sum(item.units_replenished for item in metrics),
    )


def build_simulation_summary(result: SimulationResult) -> SimulationRuntimeSummary:
    """Expose accumulated run metrics and final validation status."""
    simulation = result.scenario.simulation
    final_tick = result.simulation_summary.ticks_processed - 1
    validation = _final_validation(result, final_tick)
    metrics = result.metrics_summary
    return SimulationRuntimeSummary(
        seed=simulation.seed,
        start_datetime=simulation.start_datetime,
        end_datetime=simulation.end_datetime,
        tick_unit=simulation.tick_unit.value,
        ticks_processed=result.simulation_summary.ticks_processed,
        engine_executions=result.simulation_summary.engine_executions,
        validation_passed=validation.valid if validation is not None else False,
        demand_units=metrics.demand_units,
        unassigned_demand_units=metrics.unassigned_demand_units,
        total_transactions=metrics.total_transactions,
        completed_transactions=metrics.completed_transactions,
        partially_completed_transactions=metrics.partially_completed_transactions,
        rejected_transactions=metrics.rejected_transactions,
        transaction_lines=metrics.transaction_lines,
        completed_lines=metrics.completed_lines,
        rejected_lines=metrics.rejected_lines,
        completed_units=metrics.completed_units,
        rejected_units=metrics.rejected_units,
        net_sales_amount=metrics.net_sales_amount,
        lost_sales_amount=metrics.lost_sales_amount,
        out_of_stock_signals=metrics.out_of_stock_signals,
        replenishments_completed=metrics.replenishments_completed,
        units_replenished=metrics.units_replenished,
    )


def _final_validation(
    result: SimulationResult,
    tick_index: int,
) -> ValidationContext | None:
    if tick_index < 0 or not result.state.has_collection("validation_context"):
        return None
    value = result.state.collection("validation_context").get(f"tick-{tick_index}")
    return value if isinstance(value, ValidationContext) else None
