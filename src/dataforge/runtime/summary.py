"""Shared read-only summary extraction for public runtime surfaces."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.validation.models import ValidationContext
from dataforge.runtime.result import SimulationResult


@dataclass(frozen=True, slots=True)
class SimulationRuntimeSummary:
    """Compact official values from one completed simulation result."""

    seed: int
    start_datetime: datetime
    end_datetime: datetime
    tick_unit: str
    ticks_processed: int
    engine_executions: int
    validation_passed: bool
    completed_transactions: int | None
    rejected_transactions: int | None
    net_sales_amount: Decimal | None
    lost_sales_amount: Decimal | None


def build_simulation_summary(result: SimulationResult) -> SimulationRuntimeSummary:
    """Read final metrics and validation without recalculating business values."""
    simulation = result.scenario.simulation
    final_tick = result.simulation_summary.ticks_processed - 1
    metrics = _final_context(result, "metrics_context", final_tick, MetricsContext)
    validation = _final_context(
        result, "validation_context", final_tick, ValidationContext
    )
    return SimulationRuntimeSummary(
        seed=simulation.seed,
        start_datetime=simulation.start_datetime,
        end_datetime=simulation.end_datetime,
        tick_unit=simulation.tick_unit.value,
        ticks_processed=result.simulation_summary.ticks_processed,
        engine_executions=result.simulation_summary.engine_executions,
        validation_passed=validation.valid if validation is not None else False,
        completed_transactions=(
            metrics.completed_transactions if metrics is not None else None
        ),
        rejected_transactions=(
            metrics.rejected_transactions if metrics is not None else None
        ),
        net_sales_amount=metrics.net_sales_amount if metrics is not None else None,
        lost_sales_amount=metrics.lost_sales_amount if metrics is not None else None,
    )


def _final_context[T](
    result: SimulationResult,
    collection_name: str,
    tick_index: int,
    expected_type: type[T],
) -> T | None:
    if tick_index < 0 or not result.state.has_collection(collection_name):
        return None
    value = result.state.collection(collection_name).get(f"tick-{tick_index}")
    return value if isinstance(value, expected_type) else None
