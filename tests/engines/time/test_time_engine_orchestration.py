"""Integration tests for TimeEngine under SimulationOrchestrator."""

from datetime import datetime

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.time.engine import TimeEngine
from dataforge.engines.time.models import TemporalContext, TimeOfDay
from dataforge.runtime.orchestrator import SimulationOrchestrator


def make_runtime(
    start: datetime,
    end: datetime,
    tick_unit: TickUnit,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    event_store = EventStore()
    context = SimulationContext(
        seed=42,
        date_range=DateRange(start.date(), end.date()),
        random_engine=RandomEngine(42),
        event_bus=EventBus(event_store),
    )
    clock = SimulationClock(
        time_range=TimeRange(start=start, end=end),
        tick_unit=tick_unit,
    )
    return context, clock, event_store


def stored_temporal_contexts(context: SimulationContext) -> tuple[TemporalContext, ...]:
    values = context.state.collection("temporal_context").all()
    assert all(isinstance(value, TemporalContext) for value in values)
    return tuple(value for value in values if isinstance(value, TemporalContext))


def test_time_engine_runs_for_three_daily_ticks() -> None:
    context, clock, event_store = make_runtime(
        datetime(2026, 8, 14),
        datetime(2026, 8, 16),
        TickUnit.DAY,
    )

    summary = SimulationOrchestrator([TimeEngine()]).run(context, clock)
    temporal = stored_temporal_contexts(context)
    collection = context.state.collection("temporal_context")

    assert summary.ticks_processed == 3
    assert summary.engine_executions == 3
    assert collection.count() == 3
    assert all(collection.contains(f"tick-{index}") for index in range(3))
    assert [item.current_time for item in temporal] == [
        datetime(2026, 8, 14),
        datetime(2026, 8, 15),
        datetime(2026, 8, 16),
    ]
    assert event_store.count() == 3
    assert clock.is_finished is True


def test_time_engine_runs_for_three_hourly_lunch_ticks() -> None:
    context, clock, event_store = make_runtime(
        datetime(2026, 8, 15, 11),
        datetime(2026, 8, 15, 13),
        TickUnit.HOUR,
    )

    summary = SimulationOrchestrator([TimeEngine()]).run(context, clock)
    temporal = stored_temporal_contexts(context)

    assert summary.ticks_processed == 3
    assert summary.engine_executions == 3
    assert len(temporal) == 3
    assert all(item.time_of_day is TimeOfDay.LUNCH for item in temporal)
    assert event_store.count() == 3


def test_time_engine_runs_for_twenty_five_hourly_ticks() -> None:
    context, clock, event_store = make_runtime(
        datetime(2026, 8, 15),
        datetime(2026, 8, 16),
        TickUnit.HOUR,
    )

    summary = SimulationOrchestrator([TimeEngine()]).run(context, clock)
    temporal = stored_temporal_contexts(context)
    collection = context.state.collection("temporal_context")

    assert summary.ticks_processed == 25
    assert summary.engine_executions == 25
    assert len(temporal) == 25
    assert event_store.count() == 25
    assert collection.contains("tick-0")
    assert collection.contains("tick-24")
    assert temporal[0].current_time.isoformat() == "2026-08-15T00:00:00"
    assert temporal[-1].current_time.isoformat() == "2026-08-16T00:00:00"


def test_later_engine_reads_same_tick_temporal_context_from_state() -> None:
    observed: list[tuple[int, datetime]] = []

    class FakeTemporalConsumerEngine:
        def execute(
            self,
            context: SimulationContext,
            clock: SimulationClock,
        ) -> None:
            temporal = context.state.collection("temporal_context").require(
                f"tick-{clock.tick_index}"
            )
            assert isinstance(temporal, TemporalContext)
            observed.append((temporal.tick_index, temporal.current_time))

    context, clock, _ = make_runtime(
        datetime(2026, 8, 15, 11),
        datetime(2026, 8, 15, 13),
        TickUnit.HOUR,
    )

    SimulationOrchestrator([TimeEngine(), FakeTemporalConsumerEngine()]).run(
        context,
        clock,
    )

    assert observed == [
        (0, datetime(2026, 8, 15, 11)),
        (1, datetime(2026, 8, 15, 12)),
        (2, datetime(2026, 8, 15, 13)),
    ]
