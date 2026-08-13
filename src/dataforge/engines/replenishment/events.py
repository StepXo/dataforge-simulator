"""Events published by the replenishment engine."""

from datetime import datetime

from dataforge.core.events.event import DomainEvent
from dataforge.engines.inventory.models import InventoryMovement
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
)


class ReplenishmentScheduled(DomainEvent):
    def __init__(self, replenishment: PendingReplenishment) -> None:
        super().__init__(
            event_type="ReplenishmentScheduled",
            payload={
                "replenishment_id": replenishment.id,
                "inventory_id": replenishment.inventory_id,
                "location_id": replenishment.location_id,
                "product_id": replenishment.product_id,
                "requested_quantity": replenishment.requested_quantity,
                "requested_tick_index": replenishment.requested_tick_index,
                "due_tick_index": replenishment.due_tick_index,
                "created_at": replenishment.created_at.isoformat(),
                "status": replenishment.status.value,
            },
        )


class ReplenishmentCompleted(DomainEvent):
    def __init__(
        self,
        replenishment: PendingReplenishment,
        movement: InventoryMovement | None,
        stock_before: int,
        stock_after: int,
        completed_tick_index: int,
        occurred_at: datetime,
    ) -> None:
        super().__init__(
            event_type="ReplenishmentCompleted",
            payload={
                "replenishment_id": replenishment.id,
                "inventory_id": replenishment.inventory_id,
                "location_id": replenishment.location_id,
                "product_id": replenishment.product_id,
                "requested_quantity": replenishment.requested_quantity,
                "quantity_received": replenishment.received_quantity,
                "stock_before": stock_before,
                "stock_after": stock_after,
                "requested_tick_index": replenishment.requested_tick_index,
                "completed_tick_index": replenishment.completed_tick_index,
                "completed_at": (
                    replenishment.completed_at.isoformat()
                    if replenishment.completed_at
                    else None
                ),
                "occurred_at": occurred_at.isoformat(),
            },
        )


class ReplenishmentContextGenerated(DomainEvent):
    def __init__(self, context: ReplenishmentContext) -> None:
        super().__init__(
            event_type="ReplenishmentContextGenerated",
            payload={
                "tick_index": context.tick_index,
                "current_time": context.current_time.isoformat(),
                "replenishments_scheduled": context.replenishments_scheduled,
                "replenishments_completed": context.replenishments_completed,
                "units_received": context.units_received,
            },
        )
