"""Tests for temporal context values."""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from dataforge.core.tick import TickUnit
from dataforge.engines.time.models import TemporalContext, TimeOfDay


def make_temporal_context(current_time: datetime) -> TemporalContext:
    return TemporalContext(
        tick_index=7,
        current_time=current_time,
        tick_unit=TickUnit.HOUR,
    )


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (0, 0, TimeOfDay.EARLY_MORNING),
        (5, 59, TimeOfDay.EARLY_MORNING),
        (6, 0, TimeOfDay.MORNING),
        (10, 59, TimeOfDay.MORNING),
        (11, 0, TimeOfDay.LUNCH),
        (13, 59, TimeOfDay.LUNCH),
        (14, 0, TimeOfDay.AFTERNOON),
        (17, 59, TimeOfDay.AFTERNOON),
        (18, 0, TimeOfDay.EVENING),
        (21, 59, TimeOfDay.EVENING),
        (22, 0, TimeOfDay.NIGHT),
        (23, 59, TimeOfDay.NIGHT),
    ],
)
def test_time_of_day_boundaries(
    hour: int,
    minute: int,
    expected: TimeOfDay,
) -> None:
    temporal = make_temporal_context(datetime(2026, 8, 15, hour, minute))

    assert temporal.time_of_day is expected


def test_temporal_context_calculates_calendar_fields() -> None:
    current_time = datetime(2026, 8, 15, 12)

    temporal = make_temporal_context(current_time)

    assert temporal.tick_index == 7
    assert temporal.current_time is current_time
    assert temporal.tick_unit is TickUnit.HOUR
    assert temporal.year == 2026
    assert temporal.quarter == 3
    assert temporal.month == 8
    assert temporal.day == 15
    assert temporal.hour == 12
    assert temporal.day_of_week == 5
    assert temporal.day_name == "Saturday"
    assert temporal.is_weekend is True
    assert temporal.is_month_start is False
    assert temporal.is_month_end is False
    assert temporal.is_mid_month is True


@pytest.mark.parametrize(
    ("current_time", "day_of_week", "day_name", "is_weekend"),
    [
        (datetime(2026, 8, 14), 4, "Friday", False),
        (datetime(2026, 8, 15), 5, "Saturday", True),
        (datetime(2026, 8, 16), 6, "Sunday", True),
        (datetime(2026, 8, 17), 0, "Monday", False),
    ],
)
def test_temporal_context_uses_deterministic_english_day_names(
    current_time: datetime,
    day_of_week: int,
    day_name: str,
    is_weekend: bool,
) -> None:
    temporal = make_temporal_context(current_time)

    assert temporal.day_of_week == day_of_week
    assert temporal.day_name == day_name
    assert temporal.is_weekend is is_weekend


def test_temporal_context_detects_month_start() -> None:
    temporal = make_temporal_context(datetime(2026, 8, 1))

    assert temporal.is_month_start is True
    assert temporal.is_mid_month is False


@pytest.mark.parametrize(
    "current_time",
    [
        datetime(2026, 1, 31),
        datetime(2026, 4, 30),
        datetime(2025, 2, 28),
        datetime(2024, 2, 29),
    ],
)
def test_temporal_context_detects_month_end(current_time: datetime) -> None:
    assert make_temporal_context(current_time).is_month_end is True


def test_temporal_context_is_immutable() -> None:
    temporal = make_temporal_context(datetime(2026, 8, 15, 12))

    with pytest.raises(FrozenInstanceError):
        temporal.hour = 13
