"""Tests for the structural simulation engine contract."""

from datetime import date, datetime

from dataforge.core.engine import SimulationEngine
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore


class FakeEngine:
    """Minimal structural implementation used only by this test module."""

    def __init__(self) -> None:
        self.received_context: SimulationContext | None = None
        self.received_clock: SimulationClock | None = None

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        self.received_context = context
        self.received_clock = clock


def execute_engine(
    engine: SimulationEngine,
    context: SimulationContext,
    clock: SimulationClock,
) -> None:
    engine.execute(context, clock)


def test_structural_engine_receives_context_and_clock() -> None:
    date_range = DateRange(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )
    context = SimulationContext(
        seed=42,
        date_range=date_range,
        random_engine=RandomEngine(42),
        event_bus=EventBus(EventStore()),
    )
    clock = SimulationClock(
        time_range=TimeRange(
            start=datetime(2026, 1, 1),
            end=datetime(2026, 1, 1),
        ),
        tick_unit=TickUnit.DAY,
    )
    engine = FakeEngine()

    execute_engine(engine, context, clock)

    assert engine.received_context is context
    assert engine.received_clock is clock
