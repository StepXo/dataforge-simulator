"""Deterministic simulation clock with configurable temporal ticks."""

from datetime import datetime, timedelta
from hashlib import sha256

from dataforge.core.random_engine import RandomEngine
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import TimeRange

TICK_DELTAS = {
    TickUnit.DAY: timedelta(days=1),
    TickUnit.HOUR: timedelta(hours=1),
}


def random_times_within_tick(
    clock: "SimulationClock", seed: int, namespace: str, count: int
) -> tuple[datetime, ...]:
    """Return deterministic, chronological instants inside the current tick."""
    if count < 0:
        raise ValueError("count must be non-negative")
    tick_duration = TICK_DELTAS[clock.tick_unit]
    seconds = int(tick_duration.total_seconds())
    digest = sha256(f"{seed}:{namespace}:{clock.tick_index}".encode()).digest()
    random_engine = RandomEngine(int.from_bytes(digest[:8], "big"))
    offsets = sorted(random_engine.randint(0, seconds - 1) for _ in range(count))
    return tuple(clock.current_time + timedelta(seconds=offset) for offset in offsets)


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
