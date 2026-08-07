"""Ordered synchronous execution of simulation engines."""

from collections.abc import Sequence
from dataclasses import dataclass

from dataforge.core.engine import SimulationEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext


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
    ) -> SimulationRunSummary:
        """Run all engines for every remaining tick."""
        ticks_processed = 0
        engine_executions = 0

        while not clock.is_finished:
            for engine in self._engines:
                engine.execute(context, clock)
                engine_executions += 1
            clock.advance()
            ticks_processed += 1

        return SimulationRunSummary(
            ticks_processed=ticks_processed,
            engine_executions=engine_executions,
        )
