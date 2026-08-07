"""Apply completed transactions to immutable inventory state."""

from dataclasses import replace as replace_dataclass

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.inventory.events import (
    InventoryContextGenerated,
    InventoryMovementCreated,
    InventoryOutOfStock,
    InventoryReorderTriggered,
)
from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    InventoryMovementType,
    OutOfStockSignal,
    ReorderSignal,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import (
    Transaction,
    TransactionContext,
    TransactionLine,
    TransactionLineStatus,
)
from dataforge.inventory.models import InventoryItem
from dataforge.state.collection import StateCollection

INVENTORY_CONTEXT_COLLECTION = "inventory_context"


class InventoryEngine:
    """Apply completed sales after validating the complete tick up front."""

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        context_key = f"tick-{clock.tick_index}"
        output = self._prepare_output_collection(context, context_key)
        inventory = self._inventory_collection(context)
        temporal = self._tick_context(
            context, "temporal_context", clock.tick_index, TemporalContext
        )
        transactions = self._tick_context(
            context, "transaction_context", clock.tick_index, TransactionContext
        )
        completed = tuple(
            (transaction, line)
            for transaction in transactions.transactions
            for line in transaction.lines
            if line.status is TransactionLineStatus.COMPLETED
        )
        inventory_by_key = self._active_inventory(inventory)
        self._prevalidate(completed, inventory_by_key)

        movements: list[InventoryMovement] = []
        changed: dict[tuple[str, str], InventoryItem] = {}
        current = dict(inventory_by_key)
        for sequence, (transaction, line) in enumerate(completed, start=1):
            key = (transaction.location_id, line.product_id)
            item = current[key]
            updated = replace_dataclass(
                item, current_stock=item.current_stock - line.quantity
            )
            inventory.replace(item.id, updated)
            current[key] = updated
            changed[key] = updated
            movements.append(
                InventoryMovement(
                    id=(f"inventory-movement-{clock.tick_index}-{sequence:06d}"),
                    inventory_id=item.id,
                    location_id=item.location_id,
                    product_id=item.product_id,
                    transaction_id=transaction.id,
                    basket_id=transaction.basket_id,
                    movement_type=InventoryMovementType.SALE,
                    quantity=line.quantity,
                    stock_before=item.current_stock,
                    stock_after=updated.current_stock,
                    tick_index=clock.tick_index,
                    occurred_at=temporal.current_time,
                )
            )

        reorder_signals = tuple(
            ReorderSignal(
                item.id,
                item.location_id,
                item.product_id,
                item.current_stock,
                item.reorder_point,
                item.max_stock,
                clock.tick_index,
            )
            for item in changed.values()
            if item.current_stock <= item.reorder_point
        )
        out_of_stock_signals = tuple(
            OutOfStockSignal(
                item.id,
                item.location_id,
                item.product_id,
                clock.tick_index,
            )
            for item in changed.values()
            if item.current_stock == 0
        )
        result = InventoryContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            movements=tuple(movements),
            reorder_signals=reorder_signals,
            out_of_stock_signals=out_of_stock_signals,
            total_units_sold=sum(item.quantity for item in movements),
            inventory_items_changed=len(changed),
        )
        output.add(context_key, result)
        for movement in result.movements:
            context.event_bus.publish(InventoryMovementCreated(movement))
        for reorder_signal in result.reorder_signals:
            context.event_bus.publish(InventoryReorderTriggered(reorder_signal))
        for out_of_stock_signal in result.out_of_stock_signals:
            context.event_bus.publish(InventoryOutOfStock(out_of_stock_signal))
        context.event_bus.publish(InventoryContextGenerated(result))

    def _prepare_output_collection(
        self, context: SimulationContext, context_key: str
    ) -> StateCollection[object]:
        if context.state.has_collection(INVENTORY_CONTEXT_COLLECTION):
            collection = context.state.collection(INVENTORY_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(INVENTORY_CONTEXT_COLLECTION)
        if collection.contains(context_key):
            raise ValueError(f"InventoryEngine already executed for {context_key}")
        return collection

    def _inventory_collection(
        self, context: SimulationContext
    ) -> StateCollection[object]:
        if not context.state.has_collection("inventory"):
            raise ValueError("Required inventory collection is missing: inventory")
        collection = context.state.collection("inventory")
        values = collection.all()
        if not values:
            raise ValueError("Required inventory collection is empty: inventory")
        if any(not isinstance(value, InventoryItem) for value in values):
            raise ValueError("Inventory collection contains invalid records")
        return collection

    def _active_inventory(
        self, inventory: StateCollection[object]
    ) -> dict[tuple[str, str], InventoryItem]:
        result: dict[tuple[str, str], InventoryItem] = {}
        for value in inventory.all():
            if not isinstance(value, InventoryItem):
                raise ValueError("Inventory collection contains invalid records")
            item = value
            if not item.active:
                continue
            key = (item.location_id, item.product_id)
            if key in result:
                raise ValueError(
                    "Multiple active InventoryItems exist for commercial combination: "
                    f"{item.location_id}/{item.product_id}"
                )
            result[key] = item
        return result

    def _prevalidate(
        self,
        transactions: tuple[tuple[Transaction, TransactionLine], ...],
        inventory: dict[tuple[str, str], InventoryItem],
    ) -> None:
        accumulated: dict[tuple[str, str], int] = {}
        for transaction, line in transactions:
            if line.quantity < 1:
                raise ValueError(
                    f"Completed TransactionLine has invalid quantity: {line.id}"
                )
            key = (transaction.location_id, line.product_id)
            item = inventory.get(key)
            if item is None:
                raise ValueError(
                    "Completed Transaction references unavailable InventoryItem: "
                    f"{transaction.id}"
                )
            accumulated[key] = accumulated.get(key, 0) + line.quantity
            if accumulated[key] > item.current_stock:
                raise ValueError(
                    "Completed Transactions exceed available stock for: "
                    f"{transaction.location_id}/{line.product_id}"
                )

    def _tick_context[T](
        self,
        context: SimulationContext,
        name: str,
        tick_index: int,
        expected_type: type[T],
    ) -> T:
        if not context.state.has_collection(name):
            raise ValueError(f"Required inventory collection is missing: {name}")
        value = context.state.collection(name).get(f"tick-{tick_index}")
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for tick: {tick_index}")
        return value
