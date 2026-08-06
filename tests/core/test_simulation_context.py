"""Tests for the shared simulation context."""

from datetime import date

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore


def test_context_stores_and_reuses_its_components() -> None:
    date_range = DateRange(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
    )
    random_engine = RandomEngine(42)
    event_bus = EventBus(EventStore())

    context = SimulationContext(
        seed=42,
        date_range=date_range,
        random_engine=random_engine,
        event_bus=event_bus,
    )

    assert context.seed == 42
    assert context.date_range is date_range
    assert context.random_engine is random_engine
    assert context.event_bus is event_bus
