"""Contract for simulation engines."""

from typing import Protocol

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext


class SimulationEngine(Protocol):
    """Define the execution contract shared by simulation engines."""

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        """Execute the engine for the supplied context and clock."""
        ...
