"""Unit tests for the concrete time engine."""

from datetime import date, datetime

import pytest

from dataforge.core.engine import SimulationEngine
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.time.engine import TimeEngine
from dataforge.engines.time.events import TimeContextGenerated
from dataforge.engines.time.models import TemporalContext
from dataforge.events.event import DomainEvent
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore


def make_runtime() -> tuple[SimulationContext, SimulationClock, EventStore]:
    event_store = EventStore()
    context = SimulationContext(
        seed=42,
        date_range=DateRange(date(2026, 8, 15), date(2026, 8, 15)),
        random_engine=RandomEngine(42),
        event_bus=EventBus(event_store),
    )
    clock = SimulationClock(
        time_range=TimeRange(
            start=datetime(2026, 8, 15, 12),
            end=datetime(2026, 8, 15, 12),
        ),
        tick_unit=TickUnit.HOUR,
    )
    return context, clock, event_store


def accepts_simulation_engine(engine: SimulationEngine) -> SimulationEngine:
    return engine


def test_time_engine_stores_context_before_publishing_without_advancing_clock() -> None:
    context, clock, event_store = make_runtime()
    observed_events: list[DomainEvent] = []

    def assert_context_is_stored(event: DomainEvent) -> None:
        assert context.state.collection("temporal_context").contains("tick-0")
        observed_events.append(event)

    context.event_bus.subscribe("TimeContextGenerated", assert_context_is_stored)
    initial_time = clock.current_time
    initial_index = clock.tick_index
    engine = accepts_simulation_engine(TimeEngine())

    engine.execute(context, clock)

    collection = context.state.collection("temporal_context")
    stored = collection.require("tick-0")
    assert collection.count() == 1
    assert isinstance(stored, TemporalContext)
    assert stored.current_time == initial_time
    assert stored.tick_index == initial_index
    assert event_store.count() == 1
    assert len(observed_events) == 1
    assert isinstance(observed_events[0], TimeContextGenerated)
    assert observed_events[0].payload["current_time"] == stored.current_time.isoformat()
    assert clock.current_time == initial_time
    assert clock.tick_index == initial_index


def test_time_engine_reuses_existing_collection() -> None:
    context, clock, _ = make_runtime()
    existing = context.state.create_collection("temporal_context")

    TimeEngine().execute(context, clock)

    assert context.state.collection("temporal_context") is existing
    assert existing.contains("tick-0")


def test_duplicate_time_engine_execution_fails_without_second_event() -> None:
    context, clock, event_store = make_runtime()
    engine = TimeEngine()
    engine.execute(context, clock)

    with pytest.raises(ValueError, match="State key already exists: tick-0"):
        engine.execute(context, clock)

    assert context.state.collection("temporal_context").count() == 1
    assert event_store.count() == 1
    assert clock.current_time == datetime(2026, 8, 15, 12)
    assert clock.tick_index == 0
