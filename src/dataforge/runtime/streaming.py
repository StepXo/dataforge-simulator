"""Small post-tick collaborator for incremental operational output."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.simulation_state import require_tick_context
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.validation.models import ValidationContext
from dataforge.export.operational.builder import OperationalDataBuilder
from dataforge.export.operational.sink import OperationalDataSink
from dataforge.runtime.result import RunMetricsSummary
from dataforge.runtime.summary import RunMetricsAccumulator

HISTORICAL_CONTEXT_COLLECTIONS = (
    "temporal_context",
    "promotion_context",
    "demand_context",
    "customer_behavior_context",
    "pricing_context",
    "transaction_context",
    "inventory_context",
    "replenishment_context",
    "metrics_context",
    "validation_context",
)


class IncrementalSimulationOutput:
    """Write validated output, accumulate metrics, then evict one tick."""

    def __init__(self, sink: OperationalDataSink) -> None:
        self._sink = sink
        self._builder = OperationalDataBuilder()
        self._metrics = RunMetricsAccumulator()

    def write_master(self, context: SimulationContext) -> None:
        self._sink.write_master(self._builder.iter_master_rows(context.state))

    def write_tick(self, context: SimulationContext, clock: SimulationClock) -> None:
        tick_index = clock.tick_index
        validation = require_tick_context(
            context.state,
            "validation_context",
            tick_index,
            ValidationContext,
            owner="incremental output",
        )
        if not validation.valid:
            raise ValueError(f"Tick is not valid for incremental output: {tick_index}")
        metrics = require_tick_context(
            context.state,
            "metrics_context",
            tick_index,
            MetricsContext,
            owner="incremental output",
        )
        self._sink.write_tick(
            tick_index, self._builder.iter_tick_rows(context.state, tick_index)
        )
        self._metrics.add(metrics)
        context.state.evict_tick(tick_index, HISTORICAL_CONTEXT_COLLECTIONS)

    def write_final(self, context: SimulationContext) -> None:
        self._sink.write_final(self._builder.iter_final_rows(context.state))

    def close(self) -> None:
        self._sink.close()

    def metrics_summary(self) -> RunMetricsSummary:
        return self._metrics.summary()
