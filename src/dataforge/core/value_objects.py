"""Core domain value objects."""

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID, uuid4


def build_tick_sequence_id(prefix: str, tick_index: int, sequence: int) -> str:
    """Build the deterministic identifier format shared by tick outputs."""
    return f"{prefix}-{tick_index}-{sequence:06d}"


@dataclass(frozen=True, slots=True)
class Identifier:
    """Represent an identifier backed by a UUID."""

    value: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class DateRange:
    """Represent an inclusive calendar period."""

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")

    @property
    def days(self) -> int:
        """Return the inclusive number of days in the period."""
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Represent an inclusive datetime interval."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start_is_aware = self.start.utcoffset() is not None
        end_is_aware = self.end.utcoffset() is not None
        if start_is_aware != end_is_aware:
            raise ValueError("start and end must both be timezone-aware or both naive")
        if self.end < self.start:
            raise ValueError("end must be on or after start")
