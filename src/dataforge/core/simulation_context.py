"""Shared context for a simulation execution."""

from dataclasses import dataclass, field

from dataforge.core.random_engine import RandomEngine
from dataforge.core.value_objects import DateRange
from dataforge.events.event_bus import EventBus
from dataforge.state.simulation_state import SimulationState


@dataclass(frozen=True, slots=True)
class SimulationContext:
    """Group the core components used during a simulation."""

    seed: int
    date_range: DateRange
    random_engine: RandomEngine
    event_bus: EventBus
    state: SimulationState = field(default_factory=SimulationState)
