"""Tests for the configurable deterministic simulation clock."""

from datetime import datetime

import pytest

from dataforge.core.simulation_clock import SimulationClock
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
