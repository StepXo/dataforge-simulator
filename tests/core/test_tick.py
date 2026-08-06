"""Tests for supported simulation tick units."""

from dataforge.core.tick import TickUnit


def test_tick_units_have_serializable_values() -> None:
    assert TickUnit.DAY.value == "day"
    assert TickUnit.HOUR.value == "hour"
