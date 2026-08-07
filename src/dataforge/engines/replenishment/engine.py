"""Schedule and complete inventory replenishments across ticks."""

from dataclasses import replace as replace_dataclass
from datetime import timedelta

from pydantic import BaseModel, Field, model_validator

from dataforge.core.simulation_clock import TICK_DELTAS, SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.inventory.events import InventoryMovementCreated
from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    InventoryMovementType,
)
from dataforge.engines.replenishment.events import (
    ReplenishmentCompleted,
    ReplenishmentContextGenerated,
    ReplenishmentScheduled,
)
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
    ReplenishmentStatus,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.inventory.models import InventoryItem
from dataforge.state.collection import StateCollection

PENDING_COLLECTION = "pending_replenishments"
CONTEXT_COLLECTION = "replenishment_context"


class ReplenishmentEngineConfig(BaseModel):
    min_lead_time_days: int = Field(default=1, ge=1)
    max_lead_time_days: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "ReplenishmentEngineConfig":
        if self.max_lead_time_days < self.min_lead_time_days:
            raise ValueError("max_lead_time_days must be at least min_lead_time_days")
        return self


class ReplenishmentEngine:
    """Complete due stock receipts before scheduling new reorder signals."""

    def __init__(self, config: ReplenishmentEngineConfig | None = None) -> None:
        self._config = config or ReplenishmentEngineConfig()

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        context_key = f"tick-{clock.tick_index}"
        output = self._prepare_output(context, context_key)
        inventory_collection = self._required_collection(context, "inventory")
        inventory = self._inventory_by_id(inventory_collection)
        temporal = self._tick_context(
            context, "temporal_context", clock.tick_index, TemporalContext
        )
        inventory_context = self._tick_context(
            context, "inventory_context", clock.tick_index, InventoryContext
        )
        pending_collection = self._pending_collection(context)
        replenishments = self._pending_values(pending_collection)
        due = tuple(
            item
            for item in replenishments
            if item.status is ReplenishmentStatus.PENDING
            and item.due_tick_index <= clock.tick_index
        )
        self._prevalidate(due, inventory_context, inventory)

        completed: list[PendingReplenishment] = []
        movements: list[InventoryMovement] = []
        completion_details: list[tuple[int, int]] = []
        for item in due:
            stock = inventory[item.inventory_id]
            quantity_received = stock.max_stock - stock.current_stock
            stock_before = stock.current_stock
            if quantity_received > 0:
                updated_stock = replace_dataclass(stock, current_stock=stock.max_stock)
                inventory_collection.replace(stock.id, updated_stock)
                inventory[stock.id] = updated_stock
                movements.append(
                    InventoryMovement(
                        id=(
                            f"inventory-movement-{clock.tick_index}-"
                            f"{len(movements) + 1:06d}"
                        ),
                        inventory_id=stock.id,
                        location_id=stock.location_id,
                        product_id=stock.product_id,
                        transaction_id=None,
                        basket_id=None,
                        movement_type=InventoryMovementType.REPLENISHMENT,
                        quantity=quantity_received,
                        stock_before=stock_before,
                        stock_after=updated_stock.current_stock,
                        tick_index=clock.tick_index,
                        occurred_at=temporal.current_time,
                    )
                )
            completed_item = replace_dataclass(
                item, status=ReplenishmentStatus.COMPLETED
            )
            pending_collection.replace(item.id, completed_item)
            completed.append(completed_item)
            completion_details.append((stock_before, stock.max_stock))

        pending_inventory_ids = {
            item.inventory_id
            for item in self._pending_values(pending_collection)
            if item.status is ReplenishmentStatus.PENDING
        }
        scheduled: list[PendingReplenishment] = []
        for signal in inventory_context.reorder_signals:
            stock = inventory[signal.inventory_id]
            if (
                stock.current_stock > stock.reorder_point
                or stock.current_stock >= stock.max_stock
                or stock.id in pending_inventory_ids
            ):
                continue
            lead_time_days = context.random_engine.randint(
                self._config.min_lead_time_days,
                self._config.max_lead_time_days,
            )
            lead_time_ticks = _days_to_ticks(lead_time_days, clock)
            sequence = 1 + sum(
                item.requested_tick_index == clock.tick_index
                for item in self._pending_values(pending_collection)
            )
            replenishment = PendingReplenishment(
                id=f"replenishment-{clock.tick_index}-{sequence:06d}",
                inventory_id=stock.id,
                location_id=stock.location_id,
                product_id=stock.product_id,
                requested_quantity=stock.max_stock - stock.current_stock,
                requested_tick_index=clock.tick_index,
                due_tick_index=clock.tick_index + lead_time_ticks,
                created_at=temporal.current_time,
                status=ReplenishmentStatus.PENDING,
            )
            pending_collection.add(replenishment.id, replenishment)
            pending_inventory_ids.add(stock.id)
            scheduled.append(replenishment)

        result = ReplenishmentContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            scheduled=tuple(scheduled),
            completed=tuple(completed),
            movements=tuple(movements),
            replenishments_scheduled=len(scheduled),
            replenishments_completed=len(completed),
            units_received=sum(item.quantity for item in movements),
        )
        output.add(context_key, result)
        for movement in result.movements:
            context.event_bus.publish(InventoryMovementCreated(movement))
        movements_by_inventory = {item.inventory_id: item for item in result.movements}
        for item, (stock_before, stock_after) in zip(
            result.completed, completion_details, strict=True
        ):
            context.event_bus.publish(
                ReplenishmentCompleted(
                    item,
                    movements_by_inventory.get(item.inventory_id),
                    stock_before,
                    stock_after,
                    clock.tick_index,
                    temporal.current_time,
                )
            )
        for item in result.scheduled:
            context.event_bus.publish(ReplenishmentScheduled(item))
        context.event_bus.publish(ReplenishmentContextGenerated(result))

    def _prevalidate(
        self,
        due: tuple[PendingReplenishment, ...],
        inventory_context: InventoryContext,
        inventory: dict[str, InventoryItem],
    ) -> None:
        for item in due:
            stock = inventory.get(item.inventory_id)
            if (
                stock is None
                or not stock.active
                or stock.location_id != item.location_id
                or stock.product_id != item.product_id
                or stock.max_stock < stock.current_stock
            ):
                raise ValueError(f"Invalid due replenishment inventory: {item.id}")
        for signal in inventory_context.reorder_signals:
            stock = inventory.get(signal.inventory_id)
            if (
                stock is None
                or not stock.active
                or stock.location_id != signal.location_id
                or stock.product_id != signal.product_id
                or stock.max_stock < stock.current_stock
            ):
                raise ValueError(
                    f"Invalid ReorderSignal inventory: {signal.inventory_id}"
                )

    def _prepare_output(
        self, context: SimulationContext, key: str
    ) -> StateCollection[object]:
        if context.state.has_collection(CONTEXT_COLLECTION):
            collection = context.state.collection(CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(CONTEXT_COLLECTION)
        if collection.contains(key):
            raise ValueError(f"ReplenishmentEngine already executed for {key}")
        return collection

    def _pending_collection(
        self, context: SimulationContext
    ) -> StateCollection[object]:
        if context.state.has_collection(PENDING_COLLECTION):
            return context.state.collection(PENDING_COLLECTION)
        return context.state.create_collection(PENDING_COLLECTION)

    def _pending_values(
        self, collection: StateCollection[object]
    ) -> tuple[PendingReplenishment, ...]:
        values = collection.all()
        typed = tuple(item for item in values if isinstance(item, PendingReplenishment))
        if len(typed) != len(values):
            raise ValueError("pending_replenishments contains invalid records")
        pending_ids: set[str] = set()
        for item in typed:
            if item.status is not ReplenishmentStatus.PENDING:
                continue
            if item.inventory_id in pending_ids:
                raise ValueError(
                    "Multiple pending replenishments exist for InventoryItem: "
                    f"{item.inventory_id}"
                )
            pending_ids.add(item.inventory_id)
        return typed

    def _inventory_by_id(
        self, collection: StateCollection[object]
    ) -> dict[str, InventoryItem]:
        values = collection.all()
        typed = tuple(item for item in values if isinstance(item, InventoryItem))
        if not typed:
            raise ValueError("Required replenishment collection is empty: inventory")
        if len(typed) != len(values):
            raise ValueError("Inventory collection contains invalid records")
        return {item.id: item for item in typed}

    def _required_collection(
        self, context: SimulationContext, name: str
    ) -> StateCollection[object]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required replenishment collection is missing: {name}")
        return context.state.collection(name)

    def _tick_context[T](
        self,
        context: SimulationContext,
        name: str,
        tick_index: int,
        expected_type: type[T],
    ) -> T:
        collection = self._required_collection(context, name)
        value = collection.get(f"tick-{tick_index}")
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for tick: {tick_index}")
        return value


def _days_to_ticks(days: int, clock: SimulationClock) -> int:
    """Convert a business duration in whole days to the current tick resolution."""
    return int(timedelta(days=days) / TICK_DELTAS[clock.tick_unit])
