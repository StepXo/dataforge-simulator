"""Tests for core domain value objects."""

from datetime import UTC, date, datetime

import pytest

from dataforge.core.value_objects import DateRange, TimeRange


def test_one_day_range_has_one_inclusive_day() -> None:
    date_range = DateRange(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )

    assert date_range.days == 1


def test_multi_day_range_preserves_period() -> None:
    date_range = DateRange(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
    )

    assert date_range.start_date == date(2026, 1, 1)
    assert date_range.end_date == date(2026, 1, 7)


def test_multi_day_range_calculates_days_inclusively() -> None:
    date_range = DateRange(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
    )

    assert date_range.days == 7


def test_date_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        DateRange(
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 1),
        )


def test_time_range_preserves_single_naive_instant() -> None:
    instant = datetime(2026, 1, 1, 8)

    time_range = TimeRange(start=instant, end=instant)

    assert time_range.start is instant
    assert time_range.end is instant


def test_time_range_allows_two_naive_datetimes() -> None:
    time_range = TimeRange(
        start=datetime(2026, 1, 1, 8),
        end=datetime(2026, 1, 1, 10),
    )

    assert time_range.end > time_range.start


def test_time_range_allows_two_aware_datetimes() -> None:
    time_range = TimeRange(
        start=datetime(2026, 1, 1, 8, tzinfo=UTC),
        end=datetime(2026, 1, 1, 10, tzinfo=UTC),
    )

    assert time_range.end > time_range.start


def test_time_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="end must be on or after start"):
        TimeRange(
            start=datetime(2026, 1, 1, 10),
            end=datetime(2026, 1, 1, 8),
        )


def test_time_range_rejects_mixed_timezone_awareness() -> None:
    with pytest.raises(ValueError, match="timezone-aware or both naive"):
        TimeRange(
            start=datetime(2026, 1, 1, 8, tzinfo=UTC),
            end=datetime(2026, 1, 1, 10),
        )
