"""Supported temporal units for simulation ticks."""

from enum import StrEnum


class TickUnit(StrEnum):
    """Define the temporal granularity of a simulation tick."""

    DAY = "day"
    HOUR = "hour"
