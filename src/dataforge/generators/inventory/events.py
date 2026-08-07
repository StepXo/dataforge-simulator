"""Events published while bootstrapping inventory."""

from dataforge.core.events.event import DomainEvent
from dataforge.generators.inventory.models import InventoryItem


class InventoryItemCreated(DomainEvent):
    def __init__(self, item: InventoryItem) -> None:
        super().__init__(
            event_type="InventoryItemCreated",
            payload={
                "inventory_id": item.id,
                "location_id": item.location_id,
                "product_id": item.product_id,
                "current_stock": item.current_stock,
                "reorder_point": item.reorder_point,
                "max_stock": item.max_stock,
                "active": item.active,
            },
        )
