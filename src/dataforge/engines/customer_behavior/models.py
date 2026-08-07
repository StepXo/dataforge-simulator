"""Immutable values produced by the customer behavior engine."""

from dataclasses import dataclass
from datetime import datetime

from dataforge.customers.models import PreferredChannel


@dataclass(frozen=True, slots=True)
class PurchaseIntent:
    id: str
    customer_id: str
    location_id: str
    product_id: str
    channel: PreferredChannel
    requested_quantity: int
    demand_tick_index: int

    def __post_init__(self) -> None:
        if self.requested_quantity < 1:
            raise ValueError("requested_quantity must be at least one")


@dataclass(frozen=True, slots=True)
class CustomerBehaviorContext:
    tick_index: int
    current_time: datetime
    intents: tuple[PurchaseIntent, ...]
    total_intents: int
    total_requested_units: int
    unassigned_demand_units: int

    def __post_init__(self) -> None:
        if self.total_intents != len(self.intents):
            raise ValueError("total_intents must equal the number of intents")
        requested = sum(intent.requested_quantity for intent in self.intents)
        if self.total_requested_units != requested:
            raise ValueError("total_requested_units must equal the intent quantity sum")
        if self.unassigned_demand_units < 0:
            raise ValueError("unassigned_demand_units must be non-negative")
