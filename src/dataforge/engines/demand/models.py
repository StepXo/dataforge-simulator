"""Immutable values produced by the demand engine."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DemandRecord:
    location_id: str
    product_id: str
    expected_demand: float
    requested_units: int

    def __post_init__(self) -> None:
        if self.expected_demand < 0:
            raise ValueError("expected_demand must be non-negative")
        if self.requested_units < 0:
            raise ValueError("requested_units must be non-negative")


@dataclass(frozen=True, slots=True)
class DemandContext:
    tick_index: int
    current_time: datetime
    demands: tuple[DemandRecord, ...]
    total_requested_units: int

    def __post_init__(self) -> None:
        expected_total = sum(record.requested_units for record in self.demands)
        if self.total_requested_units != expected_total:
            raise ValueError("total_requested_units must equal the demand record sum")
