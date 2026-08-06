"""Deterministic simulation clock with configurable temporal ticks."""

from datetime import datetime, timedelta

from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import TimeRange

TICK_DELTAS = {
    TickUnit.DAY: timedelta(days=1),
    TickUnit.HOUR: timedelta(hours=1),
}


class SimulationClock:
    """Track ticks within an inclusive simulation time range."""

    def __init__(self, time_range: TimeRange, tick_unit: TickUnit) -> None:
        self._time_range = time_range
        self._tick_unit = tick_unit
        self._current_time = time_range.start
        self._tick_index = 0
        self._is_finished = False

    @property
    def time_range(self) -> TimeRange:
        """Return the complete time range for this execution."""
        return self._time_range

    @property
    def tick_unit(self) -> TickUnit:
        """Return the temporal unit used by each tick."""
        return self._tick_unit

    @property
    def current_time(self) -> datetime:
        """Return the datetime that will be processed in the current tick."""
        return self._current_time

    @property
    def tick_index(self) -> int:
        """Return the number of ticks already processed."""
        return self._tick_index

    @property
    def is_finished(self) -> bool:
        """Return whether every valid datetime has been processed."""
        return self._is_finished

    def advance(self) -> None:
        """Complete the current tick and move to the next valid datetime."""
        if self._is_finished:
            raise RuntimeError("Simulation clock has already finished.")

        self._tick_index += 1
        next_time = self._current_time + TICK_DELTAS[self._tick_unit]
        if next_time > self._time_range.end:
            self._is_finished = True
        else:
            self._current_time = next_time
