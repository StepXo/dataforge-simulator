"""Ordered synchronous bootstrap execution."""

from collections.abc import Sequence

from dataforge.bootstrap.contracts import BootstrapGenerator
from dataforge.bootstrap.models import BootstrapRunSummary
from dataforge.core.simulation_context import SimulationContext


class BootstrapRunner:
    """Execute bootstrap generators once each in stable order."""

    def __init__(self, generators: Sequence[BootstrapGenerator]) -> None:
        self._generators = tuple(generators)

    def run(self, context: SimulationContext) -> BootstrapRunSummary:
        """Run all generators and summarize their changes to state."""
        initial_collections = len(context.state.collection_names())
        initial_records = context.state.total_records
        for generator in self._generators:
            generator.generate(context)

        return BootstrapRunSummary(
            generators_executed=len(self._generators),
            collections_created=(
                len(context.state.collection_names()) - initial_collections
            ),
            records_created=context.state.total_records - initial_records,
        )
