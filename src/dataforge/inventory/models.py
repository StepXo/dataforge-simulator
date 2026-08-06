"""Immutable inventory state models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InventoryItem:
    id: str
    location_id: str
    product_id: str
    current_stock: int
    reorder_point: int
    max_stock: int
    active: bool
