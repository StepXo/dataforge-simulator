"""Events emitted after inventory state and context are stored."""

from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    OutOfStockSignal,
    ReorderSignal,
)
from dataforge.events.event import DomainEvent


class InventoryMovementCreated(DomainEvent):
    def __init__(self, movement: InventoryMovement) -> None:
        super().__init__(
            event_type="InventoryMovementCreated",
            payload={
                "movement_id": movement.id,
                "inventory_id": movement.inventory_id,
                "location_id": movement.location_id,
                "product_id": movement.product_id,
                "transaction_id": movement.transaction_id,
                "basket_id": movement.basket_id,
                "movement_type": movement.movement_type.value,
                "quantity": movement.quantity,
                "stock_before": movement.stock_before,
                "stock_after": movement.stock_after,
                "tick_index": movement.tick_index,
                "occurred_at": movement.occurred_at.isoformat(),
            },
        )


class InventoryReorderTriggered(DomainEvent):
    def __init__(self, signal: ReorderSignal) -> None:
        super().__init__(
            event_type="InventoryReorderTriggered",
            payload={
                "inventory_id": signal.inventory_id,
                "location_id": signal.location_id,
                "product_id": signal.product_id,
                "current_stock": signal.current_stock,
                "reorder_point": signal.reorder_point,
                "max_stock": signal.max_stock,
                "tick_index": signal.tick_index,
            },
        )


class InventoryOutOfStock(DomainEvent):
    def __init__(self, signal: OutOfStockSignal) -> None:
        super().__init__(
            event_type="InventoryOutOfStock",
            payload={
                "inventory_id": signal.inventory_id,
                "location_id": signal.location_id,
                "product_id": signal.product_id,
                "tick_index": signal.tick_index,
            },
        )


class InventoryContextGenerated(DomainEvent):
    def __init__(self, context: InventoryContext) -> None:
        super().__init__(
            event_type="InventoryContextGenerated",
            payload={
                "tick_index": context.tick_index,
                "current_time": context.current_time.isoformat(),
                "movement_count": len(context.movements),
                "reorder_count": len(context.reorder_signals),
                "out_of_stock_count": len(context.out_of_stock_signals),
                "total_units_sold": context.total_units_sold,
                "inventory_items_changed": context.inventory_items_changed,
            },
        )
