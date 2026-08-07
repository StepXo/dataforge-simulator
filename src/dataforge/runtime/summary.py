"""Shared read-only summary extraction for public runtime surfaces."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from dataforge.core.state.simulation_state import SimulationState
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.validation.models import ValidationContext
from dataforge.runtime.result import RunMetricsSummary, SimulationResult

ZERO = Decimal("0.00")


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


class RunMetricsAccumulator:
    """Accumulate official per-tick metrics without retaining their history."""

    def __init__(self) -> None:
        self._summary = RunMetricsSummary(
            ticks_aggregated=0,
            demand_records=0,
            demand_units=0,
            purchase_intents=0,
            intent_units=0,
            unassigned_demand_units=0,
            price_quotes=0,
            total_transactions=0,
            completed_transactions=0,
            partially_completed_transactions=0,
            rejected_transactions=0,
            transaction_lines=0,
            completed_lines=0,
            rejected_lines=0,
            completed_units=0,
            rejected_units=0,
            gross_sales_amount=ZERO,
            discount_amount=ZERO,
            net_sales_amount=ZERO,
            lost_sales_amount=ZERO,
            inventory_movements=0,
            units_removed_from_inventory=0,
            reorder_signals=0,
            out_of_stock_signals=0,
            replenishments_scheduled=0,
            replenishments_completed=0,
            units_replenished=0,
        )

    def add(self, metrics: MetricsContext) -> None:
        """Add one validated tick snapshot to the accumulated totals."""
        current = self._summary
        self._summary = replace(
            current,
            ticks_aggregated=current.ticks_aggregated + 1,
            demand_records=current.demand_records + metrics.demand_records,
            demand_units=current.demand_units + metrics.demand_units,
            purchase_intents=current.purchase_intents + metrics.purchase_intents,
            intent_units=current.intent_units + metrics.intent_units,
            unassigned_demand_units=(
                current.unassigned_demand_units + metrics.unassigned_demand_units
            ),
            price_quotes=current.price_quotes + metrics.price_quotes,
            total_transactions=current.total_transactions + metrics.total_transactions,
            completed_transactions=(
                current.completed_transactions + metrics.completed_transactions
            ),
            partially_completed_transactions=(
                current.partially_completed_transactions
                + metrics.partially_completed_transactions
            ),
            rejected_transactions=(
                current.rejected_transactions + metrics.rejected_transactions
            ),
            transaction_lines=current.transaction_lines + metrics.transaction_lines,
            completed_lines=current.completed_lines + metrics.completed_lines,
            rejected_lines=current.rejected_lines + metrics.rejected_lines,
            completed_units=current.completed_units + metrics.completed_units,
            rejected_units=current.rejected_units + metrics.rejected_units,
            gross_sales_amount=(
                current.gross_sales_amount + metrics.gross_sales_amount
            ),
            discount_amount=current.discount_amount + metrics.discount_amount,
            net_sales_amount=current.net_sales_amount + metrics.net_sales_amount,
            lost_sales_amount=current.lost_sales_amount + metrics.lost_sales_amount,
            inventory_movements=(
                current.inventory_movements + metrics.inventory_movements
            ),
            units_removed_from_inventory=(
                current.units_removed_from_inventory
                + metrics.units_removed_from_inventory
            ),
            reorder_signals=current.reorder_signals + metrics.reorder_signals,
            out_of_stock_signals=(
                current.out_of_stock_signals + metrics.out_of_stock_signals
            ),
            replenishments_scheduled=(
                current.replenishments_scheduled + metrics.replenishments_scheduled
            ),
            replenishments_completed=(
                current.replenishments_completed + metrics.replenishments_completed
            ),
            units_replenished=current.units_replenished + metrics.units_replenished,
        )

    def summary(self) -> RunMetricsSummary:
        """Return the immutable totals accumulated so far."""
        return self._summary


def aggregate_run_metrics(
    state: SimulationState,
    ticks_processed: int,
) -> RunMetricsSummary:
    """Sum every official per-tick metrics snapshot in tick order."""
    if not state.has_collection("metrics_context"):
        raise ValueError("Required runtime collection is missing: metrics_context")
    collection = state.collection("metrics_context")
    accumulator = RunMetricsAccumulator()
    for tick_index in range(ticks_processed):
        value = collection.get(f"tick-{tick_index}")
        if not isinstance(value, MetricsContext):
            raise ValueError(f"MetricsContext is missing for tick: {tick_index}")
        accumulator.add(value)
    return accumulator.summary()


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
