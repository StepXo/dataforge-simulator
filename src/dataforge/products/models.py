"""Immutable product state models."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Product:
    id: str
    name: str
    category_id: str
    currency: str
    base_price: Decimal
    base_cost: Decimal
    base_margin: Decimal
    activity_factor: float
    active: bool
