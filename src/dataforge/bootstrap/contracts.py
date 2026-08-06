"""Contract for simulation bootstrap generators."""

from typing import Protocol

from dataforge.core.simulation_context import SimulationContext


class BootstrapGenerator(Protocol):
    """Define a component that prepares initial simulation state."""

    def generate(self, context: SimulationContext) -> None:
        """Populate initial state using the shared simulation context."""
        ...
