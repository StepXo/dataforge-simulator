"""Tests for immutable inventory updates driven by completed transactions."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.customers.models import PreferredChannel
from dataforge.engines.inventory.engine import InventoryEngine
from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    InventoryMovementType,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import (
    ZERO_MONEY,
    RejectionReason,
    Transaction,
    TransactionContext,
    TransactionLine,
    TransactionLineStatus,
    TransactionStatus,
)
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.inventory.models import InventoryItem

NOW = datetime(2026, 8, 15, 12)


def transaction(
    identifier: str,
    quantity: int,
    *,
    status: TransactionStatus = TransactionStatus.COMPLETED,
    location_id: str = "location-a",
    product_id: str = "product-a",
) -> Transaction:
    amount = Decimal("10.00") * quantity
    line_status = (
        TransactionLineStatus.COMPLETED
        if status is TransactionStatus.COMPLETED
        else TransactionLineStatus.REJECTED
    )
    line = TransactionLine(
        f"line-{identifier}",
        f"intent-{identifier}",
        f"intent-{identifier}",
        product_id,
        quantity,
        Decimal("10.00"),
        amount,
        ZERO_MONEY,
        amount,
        (),
        line_status,
        None
        if line_status is TransactionLineStatus.COMPLETED
        else RejectionReason.INSUFFICIENT_STOCK,
    )
    return Transaction(
        identifier,
        "basket-0-000001",
        "customer-a",
        location_id,
        PreferredChannel.MOBILE,
        (line,),
        "COP",
        amount if line_status is TransactionLineStatus.COMPLETED else ZERO_MONEY,
        ZERO_MONEY,
        amount if line_status is TransactionLineStatus.COMPLETED else ZERO_MONEY,
        amount if line_status is TransactionLineStatus.REJECTED else ZERO_MONEY,
        quantity if line_status is TransactionLineStatus.COMPLETED else 0,
        quantity if line_status is TransactionLineStatus.REJECTED else 0,
        status,
        0,
        NOW,
    )


def transaction_context(items: tuple[Transaction, ...]) -> TransactionContext:
    lines = tuple(line for item in items for line in item.lines)
    return TransactionContext(
        0,
        NOW,
        items,
        len(items),
        sum(x.status is TransactionStatus.COMPLETED for x in items),
        sum(x.status is TransactionStatus.PARTIALLY_COMPLETED for x in items),
        sum(x.status is TransactionStatus.REJECTED for x in items),
        len(lines),
        sum(x.status is TransactionLineStatus.COMPLETED for x in lines),
        sum(x.status is TransactionLineStatus.REJECTED for x in lines),
        sum(x.completed_units for x in items),
        sum(x.rejected_units for x in items),
        sum((x.gross_amount for x in items), start=ZERO_MONEY),
        sum((x.discount_amount for x in items), start=ZERO_MONEY),
        sum((x.net_amount for x in items), start=ZERO_MONEY),
        sum((x.lost_sales_amount for x in items), start=ZERO_MONEY),
    )


def runtime(
    items: tuple[Transaction, ...] = (),
    inventory: tuple[InventoryItem, ...] | None = None,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        1,
        DateRange(date(2026, 8, 15), date(2026, 8, 15)),
        RandomEngine(1),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    values = inventory or (
        InventoryItem("inventory-a", "location-a", "product-a", 10, 3, 20, True),
    )
    inventory_collection = context.state.create_collection("inventory")
    for value in values:
        inventory_collection.add(value.id, value)
    temporal = context.state.create_collection("temporal_context")
    temporal.add("tick-0", TemporalContext(0, NOW, TickUnit.HOUR))
    transactions = context.state.create_collection("transaction_context")
    transactions.add("tick-0", transaction_context(items))
    return context, clock, store


def execute(
    items: tuple[Transaction, ...] = (),
    inventory: tuple[InventoryItem, ...] | None = None,
) -> tuple[InventoryContext, SimulationContext, EventStore]:
    context, clock, store = runtime(items, inventory)
    InventoryEngine().execute(context, clock)
    value = context.state.collection("inventory_context").require("tick-0")
    assert isinstance(value, InventoryContext)
    return value, context, store


def test_models_are_immutable_and_validate_totals() -> None:
    movement = InventoryMovement(
        "inventory-movement-0-000001",
        "inventory-a",
        "location-a",
        "product-a",
        "transaction-a",
        "basket-0-000001",
        InventoryMovementType.SALE,
        3,
        10,
        7,
        0,
        NOW,
    )
    assert InventoryContext(0, NOW, (movement,), (), (), 3, 1).total_units_sold == 3
    with pytest.raises(FrozenInstanceError):
        movement.__setattr__("quantity", 2)
    with pytest.raises(ValueError, match="total_units_sold"):
        InventoryContext(0, NOW, (movement,), (), (), 2, 1)


def test_one_sale_replaces_immutable_item_and_creates_movement() -> None:
    original = InventoryItem("inventory-a", "location-a", "product-a", 10, 3, 20, True)
    value, context, store = execute((transaction("transaction-a", 3),), (original,))
    updated = context.state.collection("inventory").require("inventory-a")
    assert isinstance(updated, InventoryItem)
    assert updated is not original and updated.current_stock == 7
    assert (updated.reorder_point, updated.max_stock, updated.active) == (3, 20, True)
    assert value.movements[0].stock_before == 10
    assert value.movements[0].stock_after == 7
    assert value.movements[0].basket_id == "basket-0-000001"
    assert store.all_events()[0].payload["basket_id"] == "basket-0-000001"


def test_multiple_sales_are_sequential_and_rejected_is_ignored() -> None:
    items = (
        transaction("transaction-a", 3),
        transaction("transaction-rejected", 5, status=TransactionStatus.REJECTED),
        transaction("transaction-c", 4),
    )
    value, context, _ = execute(items)
    assert [(x.stock_before, x.stock_after) for x in value.movements] == [
        (10, 7),
        (7, 3),
    ]
    assert [x.id for x in value.movements] == [
        "inventory-movement-0-000001",
        "inventory-movement-0-000002",
    ]
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 3
    )
    assert value.total_units_sold == 7 and value.inventory_items_changed == 1


def test_products_and_locations_have_independent_stock() -> None:
    inventory = (
        InventoryItem("ia", "location-a", "product-a", 10, 0, 20, True),
        InventoryItem("ib", "location-a", "product-b", 8, 0, 20, True),
        InventoryItem("ic", "location-b", "product-a", 6, 0, 20, True),
    )
    items = (
        transaction("ta", 2),
        transaction("tb", 3, product_id="product-b"),
        transaction("tc", 4, location_id="location-b"),
    )
    value, context, _ = execute(items, inventory)
    assert [x.current_stock for x in context.state.collection("inventory").all()] == [
        8,
        5,
        2,
    ]
    assert value.inventory_items_changed == 3


@pytest.mark.parametrize(
    "stock,reorder,quantity,reorder_count,out_count",
    [(20, 10, 12, 1, 0), (13, 10, 3, 1, 0), (20, 10, 3, 0, 0), (3, 2, 3, 1, 1)],
)
def test_reorder_and_out_of_stock_are_emitted_once_after_all_sales(
    stock: int, reorder: int, quantity: int, reorder_count: int, out_count: int
) -> None:
    item = InventoryItem(
        "inventory-a", "location-a", "product-a", stock, reorder, 30, True
    )
    value, _, store = execute((transaction("ta", quantity),), (item,))
    assert len(value.reorder_signals) == reorder_count
    assert len(value.out_of_stock_signals) == out_count
    event_types = [event.event_type for event in store.all_events()]
    assert event_types.count("InventoryReorderTriggered") == reorder_count
    assert event_types.count("InventoryOutOfStock") == out_count


def test_empty_and_rejected_only_contexts_do_not_change_stock_or_signal() -> None:
    for items in ((), (transaction("tr", 5, status=TransactionStatus.REJECTED),)):
        value, context, store = execute(items)
        assert value == InventoryContext(0, NOW, (), (), (), 0, 0)
        assert (
            context.state.collection("inventory").require("inventory-a").current_stock
            == 10
        )
        assert [event.event_type for event in store.all_events()] == [
            "InventoryContextGenerated"
        ]


def test_overselling_is_prevalidated_before_any_mutation() -> None:
    context, clock, store = runtime(
        (transaction("ta", 4), transaction("tb", 4)),
        (InventoryItem("inventory-a", "location-a", "product-a", 5, 0, 10, True),),
    )
    with pytest.raises(ValueError, match="exceed available stock"):
        InventoryEngine().execute(context, clock)
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 5
    )
    assert store.count() == 0


@pytest.mark.parametrize(
    "inventory",
    [
        (InventoryItem("other", "location-x", "product-a", 10, 0, 20, True),),
        (InventoryItem("inventory-a", "location-a", "product-a", 10, 0, 20, False),),
    ],
)
def test_unavailable_inventory_fails_before_mutation(
    inventory: tuple[InventoryItem, ...],
) -> None:
    context, clock, store = runtime((transaction("ta", 2),), inventory)
    before = context.state.collection("inventory").all()
    with pytest.raises(ValueError, match="unavailable InventoryItem"):
        InventoryEngine().execute(context, clock)
    assert context.state.collection("inventory").all() == before
    assert store.count() == 0


def test_duplicate_execution_fails_before_second_stock_change_or_event() -> None:
    context, clock, store = runtime((transaction("ta", 3),))
    engine = InventoryEngine()
    engine.execute(context, clock)
    before_events = store.count()
    with pytest.raises(ValueError, match="already executed"):
        engine.execute(context, clock)
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 7
    )
    assert store.count() == before_events


def test_updated_stock_persists_into_the_next_tick() -> None:
    context, clock, _ = runtime((transaction("tick-zero", 3),))
    engine = InventoryEngine()
    engine.execute(context, clock)
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 7
    )

    clock.advance()
    context.state.collection("temporal_context").add(
        "tick-1", TemporalContext(1, NOW, TickUnit.HOUR)
    )
    next_transactions = transaction_context((transaction("tick-one", 3),))
    context.state.collection("transaction_context").add(
        "tick-1",
        replace(next_transactions, tick_index=1),
    )
    engine.execute(context, clock)

    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 4
    )
    second = context.state.collection("inventory_context").require("tick-1")
    assert isinstance(second, InventoryContext)
    assert (second.movements[0].stock_before, second.movements[0].stock_after) == (7, 4)


@pytest.mark.parametrize("collection_name", ["temporal_context", "transaction_context"])
def test_current_tick_dependencies_are_required(collection_name: str) -> None:
    context, clock, _ = runtime()
    context.state.collection(collection_name).remove("tick-0")
    with pytest.raises(ValueError, match=f"{collection_name} context is missing"):
        InventoryEngine().execute(context, clock)
