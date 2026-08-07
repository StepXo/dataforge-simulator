"""Temporal values produced by the time engine."""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from dataforge.core.tick import TickUnit

DAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class TimeOfDay(StrEnum):
    """Classify an hour into a deterministic generic period."""

    EARLY_MORNING = "early_morning"
    MORNING = "morning"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


def time_of_day_for_hour(hour: int) -> TimeOfDay:
    """Classify one wall-clock hour using the shared daypart boundaries."""
    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")
    if hour < 6:
        return TimeOfDay.EARLY_MORNING
    if hour < 11:
        return TimeOfDay.MORNING
    if hour < 14:
        return TimeOfDay.LUNCH
    if hour < 18:
        return TimeOfDay.AFTERNOON
    if hour < 22:
        return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


@dataclass(frozen=True, slots=True)
class TemporalContext:
    """Describe the deterministic temporal characteristics of one tick."""

    tick_index: int
    current_time: datetime
    tick_unit: TickUnit
    year: int = field(init=False)
    quarter: int = field(init=False)
    month: int = field(init=False)
    day: int = field(init=False)
    hour: int = field(init=False)
    day_of_week: int = field(init=False)
    day_name: str = field(init=False)
    time_of_day: TimeOfDay = field(init=False)
    is_weekend: bool = field(init=False)
    is_month_start: bool = field(init=False)
    is_month_end: bool = field(init=False)
    is_mid_month: bool = field(init=False)

    def __post_init__(self) -> None:
        day_of_week = self.current_time.weekday()
        object.__setattr__(self, "year", self.current_time.year)
        object.__setattr__(self, "quarter", (self.current_time.month - 1) // 3 + 1)
        object.__setattr__(self, "month", self.current_time.month)
        object.__setattr__(self, "day", self.current_time.day)
        object.__setattr__(self, "hour", self.current_time.hour)
        object.__setattr__(self, "day_of_week", day_of_week)
        object.__setattr__(self, "day_name", DAY_NAMES[day_of_week])
        object.__setattr__(
            self, "time_of_day", time_of_day_for_hour(self.current_time.hour)
        )
        object.__setattr__(self, "is_weekend", day_of_week >= 5)
        object.__setattr__(self, "is_month_start", self.current_time.day == 1)
        object.__setattr__(
            self,
            "is_month_end",
            self.current_time.day
            == monthrange(self.current_time.year, self.current_time.month)[1],
        )
        object.__setattr__(self, "is_mid_month", self.current_time.day == 15)
