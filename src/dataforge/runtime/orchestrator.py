"""Ordered synchronous execution of simulation engines."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dataforge.core.engine import SimulationEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext

PostTickHook = Callable[[SimulationContext, SimulationClock], None]


@dataclass(frozen=True, slots=True)
class SimulationRunSummary:
    """Summarize the work completed by one orchestrator run."""

    ticks_processed: int
    engine_executions: int


class SimulationOrchestrator:
    """Execute each engine in order once per temporal tick."""

    def __init__(self, engines: Sequence[SimulationEngine]) -> None:
        self._engines = tuple(engines)

    def run(
        self,
        context: SimulationContext,
        clock: SimulationClock,
        post_tick: PostTickHook | None = None,
    ) -> SimulationRunSummary:
        """Run all engines and an optional successful post-tick action."""
        ticks_processed = 0
        engine_executions = 0

        while not clock.is_finished:
            for engine in self._engines:
                engine.execute(context, clock)
                engine_executions += 1
            if post_tick is not None:
                post_tick(context, clock)
            clock.advance()
            ticks_processed += 1

        return SimulationRunSummary(
            ticks_processed=ticks_processed,
            engine_executions=engine_executions,
        )
