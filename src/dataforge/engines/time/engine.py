"""Engine that interprets the current simulated time."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.time.events import TimeContextGenerated
from dataforge.engines.time.models import TemporalContext

TEMPORAL_CONTEXT_COLLECTION = "temporal_context"


class TimeEngine:
    """Generate, store, and announce temporal context for each tick."""

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        """Interpret the current tick without advancing the clock."""
        temporal_context = TemporalContext(
            tick_index=clock.tick_index,
            current_time=clock.current_time,
            tick_unit=clock.tick_unit,
        )
        if context.state.has_collection(TEMPORAL_CONTEXT_COLLECTION):
            collection = context.state.collection(TEMPORAL_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(TEMPORAL_CONTEXT_COLLECTION)

        collection.add(f"tick-{clock.tick_index}", temporal_context)
        context.event_bus.publish(TimeContextGenerated(temporal_context))
