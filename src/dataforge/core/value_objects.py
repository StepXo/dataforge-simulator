"""Core domain value objects."""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4


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
