"""Tests for ordered simulation orchestration."""

from datetime import date, datetime

import pytest

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.runtime.orchestrator import SimulationOrchestrator


def make_context() -> SimulationContext:
    return SimulationContext(
        seed=42,
        date_range=DateRange(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        ),
        random_engine=RandomEngine(42),
        event_bus=EventBus(EventStore()),
    )


def make_clock() -> SimulationClock:
    return SimulationClock(
        time_range=TimeRange(
            start=datetime(2026, 1, 1),
            end=datetime(2026, 1, 3),
        ),
        tick_unit=TickUnit.DAY,
    )


class RecordingEngine:
    def __init__(
        self,
        name: str,
        executions: list[tuple[int, datetime, str]],
    ) -> None:
        self.name = name
        self.executions = executions

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        self.executions.append((clock.tick_index, clock.current_time, self.name))


def test_runs_every_engine_once_per_tick_in_stable_order() -> None:
    executions: list[tuple[int, datetime, str]] = []
    first = RecordingEngine("A", executions)
    second = RecordingEngine("B", executions)
    clock = make_clock()

    summary = SimulationOrchestrator([first, second]).run(make_context(), clock)

    assert executions == [
        (0, datetime(2026, 1, 1), "A"),
        (0, datetime(2026, 1, 1), "B"),
        (1, datetime(2026, 1, 2), "A"),
        (1, datetime(2026, 1, 2), "B"),
        (2, datetime(2026, 1, 3), "A"),
        (2, datetime(2026, 1, 3), "B"),
    ]
    assert summary.ticks_processed == 3
    assert summary.engine_executions == 6
    assert clock.tick_index == 3
    assert clock.is_finished is True


def test_empty_engine_collection_still_processes_every_tick() -> None:
    clock = make_clock()

    summary = SimulationOrchestrator([]).run(make_context(), clock)

    assert summary.ticks_processed == 3
    assert summary.engine_executions == 0
    assert clock.is_finished is True


def test_engine_error_stops_tick_without_advancing_clock() -> None:
    executions: list[tuple[int, datetime, str]] = []
    error = ValueError("engine failed")

    class FailingEngine:
        def execute(
            self,
            context: SimulationContext,
            clock: SimulationClock,
        ) -> None:
            executions.append((clock.tick_index, clock.current_time, "B"))
            raise error

    engines = [
        RecordingEngine("A", executions),
        FailingEngine(),
        RecordingEngine("C", executions),
    ]
    clock = make_clock()

    with pytest.raises(ValueError) as raised:
        SimulationOrchestrator(engines).run(make_context(), clock)

    assert raised.value is error
    assert executions == [
        (0, datetime(2026, 1, 1), "A"),
        (0, datetime(2026, 1, 1), "B"),
    ]
    assert clock.tick_index == 0
    assert clock.current_time == datetime(2026, 1, 1)


def test_engine_can_produce_many_actions_during_each_execution() -> None:
    actions: list[str] = []

    class MultipleActionEngine:
        def __init__(self) -> None:
            self.execution_count = 0

        def execute(
            self,
            context: SimulationContext,
            clock: SimulationClock,
        ) -> None:
            self.execution_count += 1
            actions.extend(
                f"tick-{clock.tick_index}-action-{index}" for index in range(5)
            )

    engine = MultipleActionEngine()

    summary = SimulationOrchestrator([engine]).run(make_context(), make_clock())

    assert engine.execution_count == 3
    assert summary.engine_executions == 3
    assert len(actions) == 15


def test_post_tick_error_prevents_clock_advance() -> None:
    clock = make_clock()
    error = OSError("sink failed")

    def fail_after_tick(
        context: SimulationContext, current_clock: SimulationClock
    ) -> None:
        assert current_clock.tick_index == 0
        raise error

    with pytest.raises(OSError) as raised:
        SimulationOrchestrator([]).run(make_context(), clock, post_tick=fail_after_tick)

    assert raised.value is error
    assert clock.tick_index == 0
    assert clock.current_time == datetime(2026, 1, 1)
