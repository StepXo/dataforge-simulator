"""Immutable inventory movement results produced for one tick."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InventoryMovementType(StrEnum):
    SALE = "sale"
    REPLENISHMENT = "replenishment"


@dataclass(frozen=True, slots=True)
class InventoryMovement:
    id: str
    inventory_id: str
    location_id: str
    product_id: str
    transaction_id: str | None
    basket_id: str | None
    movement_type: InventoryMovementType
    quantity: int
    stock_before: int
    stock_after: int
    tick_index: int
    occurred_at: datetime
    replenishment_id: str | None = None

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("InventoryMovement quantity must be at least one")
        if self.stock_before < 0 or self.stock_after < 0:
            raise ValueError("InventoryMovement stock cannot be negative")
        if self.movement_type is InventoryMovementType.SALE:
            if self.transaction_id is None or self.basket_id is None:
                raise ValueError("Sale movement requires transaction and basket IDs")
            if self.replenishment_id is not None:
                raise ValueError("Sale movement cannot reference a replenishment")
            expected_stock = self.stock_before - self.quantity
        else:
            if self.transaction_id is not None or self.basket_id is not None:
                raise ValueError(
                    "Replenishment movement cannot reference a transaction"
                )
            if self.replenishment_id is None:
                raise ValueError("Replenishment movement requires replenishment ID")
            expected_stock = self.stock_before + self.quantity
        if expected_stock != self.stock_after:
            raise ValueError("InventoryMovement stock values are inconsistent")


@dataclass(frozen=True, slots=True)
class ReorderSignal:
    inventory_id: str
    location_id: str
    product_id: str
    current_stock: int
    reorder_point: int
    max_stock: int
    tick_index: int


@dataclass(frozen=True, slots=True)
class OutOfStockSignal:
    inventory_id: str
    location_id: str
    product_id: str
    tick_index: int


@dataclass(frozen=True, slots=True)
class InventoryContext:
    tick_index: int
    current_time: datetime
    movements: tuple[InventoryMovement, ...]
    reorder_signals: tuple[ReorderSignal, ...]
    out_of_stock_signals: tuple[OutOfStockSignal, ...]
    total_units_sold: int
    inventory_items_changed: int

    def __post_init__(self) -> None:
        if self.total_units_sold != sum(item.quantity for item in self.movements):
            raise ValueError("total_units_sold is inconsistent")
        changed = {(item.location_id, item.product_id) for item in self.movements}
        if self.inventory_items_changed != len(changed):
            raise ValueError("inventory_items_changed is inconsistent")
