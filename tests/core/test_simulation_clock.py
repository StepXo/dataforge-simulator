"""Tests for the configurable deterministic simulation clock."""

from datetime import datetime

import pytest

from dataforge.core.simulation_clock import (
    TICK_DELTAS,
    SimulationClock,
    random_times_within_tick,
)
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import TimeRange


def make_clock(
    start: datetime,
    end: datetime,
    tick_unit: TickUnit,
) -> SimulationClock:
    return SimulationClock(
        time_range=TimeRange(start=start, end=end),
        tick_unit=tick_unit,
    )


def test_initial_state_preserves_configuration() -> None:
    time_range = TimeRange(
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 3),
    )

    clock = SimulationClock(time_range=time_range, tick_unit=TickUnit.DAY)

    assert clock.time_range is time_range
    assert clock.tick_unit is TickUnit.DAY
    assert clock.current_time == time_range.start
    assert clock.tick_index == 0
    assert clock.is_finished is False


def test_daily_ticks_are_inclusive_and_never_exceed_end() -> None:
    end = datetime(2026, 1, 3)
    clock = make_clock(datetime(2026, 1, 1), end, TickUnit.DAY)
    observed_times: list[datetime] = []

    while not clock.is_finished:
        observed_times.append(clock.current_time)
        clock.advance()
        assert clock.current_time <= end

    assert observed_times == [
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
        datetime(2026, 1, 3),
    ]
    assert clock.tick_index == 3
    assert clock.current_time == end

    with pytest.raises(RuntimeError, match="Simulation clock has already finished"):
        clock.advance()


def test_hourly_ticks_are_inclusive_and_never_exceed_end() -> None:
    end = datetime(2026, 1, 1, 10)
    clock = make_clock(datetime(2026, 1, 1, 8), end, TickUnit.HOUR)
    observed_times: list[datetime] = []

    while not clock.is_finished:
        observed_times.append(clock.current_time)
        clock.advance()
        assert clock.current_time <= end

    assert observed_times == [
        datetime(2026, 1, 1, 8),
        datetime(2026, 1, 1, 9),
        datetime(2026, 1, 1, 10),
    ]
    assert clock.tick_index == 3
    assert clock.current_time == end

    with pytest.raises(RuntimeError):
        clock.advance()


def test_hourly_ticks_across_two_midnights_total_twenty_five() -> None:
    clock = make_clock(
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
        TickUnit.HOUR,
    )

    while not clock.is_finished:
        clock.advance()

    assert clock.tick_index == 25
    assert clock.current_time == datetime(2026, 1, 2)


@pytest.mark.parametrize("tick_unit", [TickUnit.HOUR, TickUnit.DAY])
def test_random_times_are_reproducible_ordered_and_inside_tick(
    tick_unit: TickUnit,
) -> None:
    start = datetime(2026, 1, 1, 10)
    end = start + TICK_DELTAS[tick_unit]
    clock = make_clock(start, end, tick_unit)

    first = random_times_within_tick(clock, 42, "test", 8)
    second = random_times_within_tick(clock, 42, "test", 8)
    different = random_times_within_tick(clock, 137, "test", 8)

    assert first == second
    assert first != different
    assert first == tuple(sorted(first))
    assert all(start <= occurred_at < end for occurred_at in first)


def test_random_times_reject_negative_count() -> None:
    start = datetime(2026, 1, 1, 10)
    clock = make_clock(start, start, TickUnit.HOUR)
    with pytest.raises(ValueError, match="non-negative"):
        random_times_within_tick(clock, 42, "test", -1)
