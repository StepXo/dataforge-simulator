"""Immutable successful state validation result."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ValidationContext:
    tick_index: int
    current_time: datetime
    checks_executed: int
    collections_checked: int
    valid: bool
