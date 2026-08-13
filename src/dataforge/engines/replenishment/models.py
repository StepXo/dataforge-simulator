"""Immutable replenishment scheduling and tick results."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dataforge.engines.inventory.models import InventoryMovement


class ReplenishmentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class PendingReplenishment:
    id: str
    inventory_id: str
    location_id: str
    product_id: str
    requested_quantity: int
    requested_tick_index: int
    due_tick_index: int
    created_at: datetime
    status: ReplenishmentStatus
    completed_tick_index: int | None = None
    completed_at: datetime | None = None
    received_quantity: int | None = None

    def __post_init__(self) -> None:
        if self.requested_quantity < 1:
            raise ValueError("requested_quantity must be at least one")
        if self.due_tick_index <= self.requested_tick_index:
            raise ValueError("due_tick_index must follow requested_tick_index")
        completion = (
            self.completed_tick_index,
            self.completed_at,
            self.received_quantity,
        )
        if self.status is ReplenishmentStatus.PENDING and any(
            value is not None for value in completion
        ):
            raise ValueError("Pending replenishment cannot contain completion facts")
        if self.status is ReplenishmentStatus.COMPLETED and any(
            value is None for value in completion
        ):
            raise ValueError("Completed replenishment requires completion facts")
        if self.completed_tick_index is not None and self.completed_tick_index < 0:
            raise ValueError("completed_tick_index cannot be negative")
        if self.received_quantity is not None and self.received_quantity < 0:
            raise ValueError("received_quantity cannot be negative")


@dataclass(frozen=True, slots=True)
class ReplenishmentContext:
    tick_index: int
    current_time: datetime
    scheduled: tuple[PendingReplenishment, ...]
    completed: tuple[PendingReplenishment, ...]
    movements: tuple[InventoryMovement, ...]
    replenishments_scheduled: int
    replenishments_completed: int
    units_received: int

    def __post_init__(self) -> None:
        if self.replenishments_scheduled != len(self.scheduled):
            raise ValueError("replenishments_scheduled is inconsistent")
        if self.replenishments_completed != len(self.completed):
            raise ValueError("replenishments_completed is inconsistent")
        if self.units_received != sum(item.quantity for item in self.movements):
            raise ValueError("units_received is inconsistent")
