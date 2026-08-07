"""Small helpers shared by bootstrap generators."""

from collections.abc import Sequence

from dataforge.core.state.simulation_state import SimulationState


def prepare_empty_collections(state: SimulationState, names: Sequence[str]) -> None:
    """Create missing collections and reject existing non-empty collections."""
    for name in names:
        if state.has_collection(name) and state.collection(name).count() > 0:
            raise ValueError(f"State collection must be empty: {name}")
    for name in names:
        if not state.has_collection(name):
            state.create_collection(name)
