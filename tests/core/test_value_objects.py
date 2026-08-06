"""Tests for core domain value objects."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from dataforge.core.value_objects import DateRange, Identifier


def test_identifier_generates_uuid() -> None:
    assert isinstance(Identifier().value, UUID)


def test_identifier_preserves_supplied_uuid() -> None:
    value = uuid4()

    assert Identifier(value=value).value == value


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
