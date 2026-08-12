"""Tests for all-or-nothing transaction decisions."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import TICK_DELTAS, SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.inventory.engine import InventoryEngine
from dataforge.engines.inventory.models import InventoryContext
from dataforge.engines.pricing.models import PriceQuote, PricingContext
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.engine import TransactionEngine
from dataforge.engines.transaction.models import (
    ZERO_MONEY,
    RejectionReason,
    TransactionContext,
    TransactionStatus,
)
from dataforge.generators.customers.models import (
    Customer,
    CustomerSegment,
    PreferredChannel,
)
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product

NOW = datetime(2026, 8, 15, 12)


def purchase_intent(
    identifier: str,
    quantity: int = 3,
    product_id: str = "product-a",
    location_id: str = "location-a",
    basket_id: str = "basket-0-000001",
) -> PurchaseIntent:
    return PurchaseIntent(
        identifier,
        basket_id,
        "customer-a",
        location_id,
        product_id,
        PreferredChannel.MOBILE,
        quantity,
        0,
    )


def quote(intent: PurchaseIntent, net: Decimal | None = None) -> PriceQuote:
    gross = Decimal("100.00") * intent.requested_quantity
    discount = Decimal("10.00") * intent.requested_quantity
    effective_net = (
        net if net is not None else Decimal("90.00") * intent.requested_quantity
    )
    return PriceQuote(
        intent.id,
        intent.basket_id,
        intent.customer_id,
        intent.location_id,
        intent.product_id,
        intent.channel,
        intent.requested_quantity,
        "COP",
        Decimal("100.00"),
        Decimal("10.00"),
        Decimal("90.00"),
        gross,
        discount,
        effective_net,
        ("promotion-a",),
        0,
    )


def runtime(
    *,
    intents: tuple[PurchaseIntent, ...] | None = None,
    quotes: tuple[PriceQuote, ...] | None = None,
    inventory: tuple[InventoryItem, ...] | None = None,
    opened_at: date = date(2020, 1, 1),
    product_active: bool = True,
    seed: int = 42,
    tick_unit: TickUnit = TickUnit.HOUR,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    selected_intents = (
        intents if intents is not None else (purchase_intent("intent-a"),)
    )
    selected_quotes = (
        quotes
        if quotes is not None
        else tuple(quote(item) for item in selected_intents)
    )
    selected_inventory = (
        inventory
        if inventory is not None
        else (InventoryItem("inventory-a", "location-a", "product-a", 5, 0, 10, True),)
    )
    store = EventStore()
    context = SimulationContext(
        seed, DateRange(NOW.date(), NOW.date()), RandomEngine(seed), EventBus(store)
    )
    clock = SimulationClock(TimeRange(NOW, NOW), tick_unit)
    customer = Customer(
        "customer-a",
        "city-a",
        "region-a",
        "location-a",
        CustomerSegment.REGULAR,
        2.0,
        PreferredChannel.MOBILE,
        0.5,
        1.0,
        date(2020, 1, 1),
        True,
    )
    location = Location(
        "location-a",
        "A",
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        100,
        1.0,
        opened_at,
    )
    product = Product(
        "product-a",
        "A",
        "category-a",
        "COP",
        Decimal("100.00"),
        Decimal("50.00"),
        Decimal("0.5000"),
        1.0,
        product_active,
    )
    context.state.create_collection("customers").add(customer.id, customer)
    context.state.create_collection("locations").add(location.id, location)
    context.state.create_collection("products").add(product.id, product)
    inv = context.state.create_collection("inventory")
    for item in selected_inventory:
        inv.add(item.id, item)
    context.state.create_collection("temporal_context").add(
        "tick-0", TemporalContext(0, NOW, tick_unit)
    )
    context.state.create_collection("customer_behavior_context").add(
        "tick-0",
        CustomerBehaviorContext(
            0,
            NOW,
            selected_intents,
            len(selected_intents),
            sum(item.requested_quantity for item in selected_intents),
            0,
        ),
    )
    context.state.create_collection("pricing_context").add(
        "tick-0",
        PricingContext(
            0,
            NOW,
            "COP" if selected_quotes else None,
            selected_quotes,
            sum((item.gross_amount for item in selected_quotes), start=ZERO_MONEY),
            sum((item.discount_amount for item in selected_quotes), start=ZERO_MONEY),
            sum((item.net_amount for item in selected_quotes), start=ZERO_MONEY),
        ),
    )
    return context, clock, store


def result(
    **kwargs: object,
) -> tuple[TransactionContext, SimulationContext, EventStore]:
    context, clock, store = runtime(**kwargs)
    TransactionEngine().execute(context, clock)
    value = context.state.collection("transaction_context").require("tick-0")
    assert isinstance(value, TransactionContext)
    return value, context, store


@pytest.mark.parametrize("stock", [5, 3])
def test_sufficient_and_exact_stock_complete(stock: int) -> None:
    value, context, _ = result(
        inventory=(InventoryItem("i", "location-a", "product-a", stock, 0, 10, True),)
    )
    transaction = value.transactions[0]
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.basket_id == "basket-0-000001"
    assert transaction.rejection_reason is None
    assert value.completed_units == 3 and value.net_amount == Decimal("270.00")
    assert context.state.collection("inventory").require("i").current_stock == stock


def test_promoted_line_keeps_gross_unit_price() -> None:
    intent = purchase_intent("intent-a", 2)
    promoted = PriceQuote(
        intent.id,
        intent.basket_id,
        intent.customer_id,
        intent.location_id,
        intent.product_id,
        intent.channel,
        2,
        "COP",
        Decimal("25000.00"),
        Decimal("3872.50"),
        Decimal("21127.50"),
        Decimal("50000.00"),
        Decimal("7745.00"),
        Decimal("42255.00"),
        ("promotion-a",),
        0,
    )
    value, _, _ = result(
        intents=(intent,),
        quotes=(promoted,),
        inventory=(InventoryItem("i", "location-a", "product-a", 5, 0, 10, True),),
    )
    line = value.transactions[0].lines[0]
    assert line.unit_price == Decimal("25000.00")
    assert line.gross_amount == line.unit_price * line.quantity
    assert line.net_amount == line.gross_amount - line.discount_amount


@pytest.mark.parametrize("stock", [5, 0])
def test_line_money_invariants_apply_to_completed_and_rejected(stock: int) -> None:
    value, _, _ = result(
        inventory=(InventoryItem("i", "location-a", "product-a", stock, 0, 10, True),)
    )
    line = value.transactions[0].lines[0]
    assert line.unit_price == Decimal("100.00")
    assert line.gross_amount == line.unit_price * line.quantity
    assert line.net_amount == line.gross_amount - line.discount_amount


@pytest.mark.parametrize("tick_unit", [TickUnit.HOUR, TickUnit.DAY])
def test_transactions_receive_reproducible_intratick_timestamps(
    tick_unit: TickUnit,
) -> None:
    intents = (
        purchase_intent("intent-a", 1, basket_id="basket-0-000001"),
        purchase_intent("intent-b", 1, basket_id="basket-0-000002"),
        purchase_intent("intent-c", 1, basket_id="basket-0-000003"),
    )
    first, first_context, _ = result(intents=intents, seed=42, tick_unit=tick_unit)
    second, _, _ = result(intents=intents, seed=42, tick_unit=tick_unit)
    different, _, _ = result(intents=intents, seed=137, tick_unit=tick_unit)
    duration = TICK_DELTAS[tick_unit]
    timestamps = tuple(item.occurred_at for item in first.transactions)

    assert timestamps == tuple(item.occurred_at for item in second.transactions)
    assert timestamps != tuple(item.occurred_at for item in different.transactions)
    assert timestamps == tuple(sorted(timestamps))
    assert all(NOW <= occurred_at < NOW + duration for occurred_at in timestamps)
    assert any(occurred_at != NOW for occurred_at in timestamps)
    location = first_context.state.collection("locations").require("location-a")
    assert all(occurred_at.date() >= location.opened_at for occurred_at in timestamps)


@pytest.mark.parametrize("stock", [2, 0])
def test_insufficient_and_zero_stock_reject(stock: int) -> None:
    value, _, _ = result(
        inventory=(InventoryItem("i", "location-a", "product-a", stock, 0, 10, True),)
    )
    transaction = value.transactions[0]
    assert transaction.status is TransactionStatus.REJECTED
    assert transaction.rejection_reason is RejectionReason.INSUFFICIENT_STOCK
    assert transaction.quantity == 3
    assert value.lost_sales_amount == Decimal("270.00")
    assert value.net_amount == ZERO_MONEY


@pytest.mark.parametrize(
    "inventory",
    [
        (InventoryItem("other", "location-other", "product-a", 5, 0, 10, True),),
        (InventoryItem("i", "location-a", "product-a", 5, 0, 10, False),),
    ],
)
def test_inventory_unavailable_rejects(inventory: tuple[InventoryItem, ...]) -> None:
    value, _, _ = result(inventory=inventory)
    transaction = value.transactions[0]
    assert transaction.rejection_reason is RejectionReason.INVENTORY_UNAVAILABLE


def test_local_ledger_prevents_overselling_and_preserves_order() -> None:
    first, second = purchase_intent("intent-a", 4), purchase_intent("intent-b", 4)
    value, context, store = result(
        intents=(first, second),
        inventory=(InventoryItem("i", "location-a", "product-a", 5, 0, 10, True),),
    )
    assert len(value.transactions) == 1
    transaction = value.transactions[0]
    assert transaction.status is TransactionStatus.PARTIALLY_COMPLETED
    assert [line.status.value for line in transaction.lines] == [
        "completed",
        "rejected",
    ]
    assert value.total_transactions == 1
    assert value.partially_completed_transactions == 1
    assert value.transaction_lines == 2
    assert value.completed_units == 4 and value.rejected_units == 4
    assert value.net_amount == Decimal("360.00")
    assert value.lost_sales_amount == Decimal("360.00")
    assert context.state.collection("inventory").require("i").current_stock == 5
    assert [event.event_type for event in store.all_events()] == [
        "TransactionPartiallyCompleted",
        "TransactionContextGenerated",
    ]
    assert store.all_events()[0].payload["basket_id"] == "basket-0-000001"
    InventoryEngine().execute(
        context, SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    )
    inventory_context = context.state.collection("inventory_context").require("tick-0")
    assert isinstance(inventory_context, InventoryContext)
    assert len(inventory_context.movements) == 1
    assert inventory_context.movements[0].occurred_at == transaction.occurred_at
    assert inventory_context.total_units_sold == 4
    assert context.state.collection("inventory").require("i").current_stock == 1


def test_ledger_is_independent_by_product_and_location() -> None:
    first = purchase_intent("intent-a", 4)
    second = purchase_intent("intent-b", 4, product_id="product-b")
    context, clock, _ = runtime(
        intents=(first, second), quotes=(quote(first), quote(second))
    )
    product_b = Product(
        "product-b",
        "B",
        "category-a",
        "COP",
        Decimal("100"),
        Decimal("50"),
        Decimal("0.5000"),
        1.0,
        True,
    )
    context.state.collection("products").add(product_b.id, product_b)
    context.state.collection("inventory").add(
        "ib", InventoryItem("ib", "location-a", "product-b", 4, 0, 10, True)
    )
    TransactionEngine().execute(context, clock)
    value = context.state.collection("transaction_context").require("tick-0")
    assert all(
        item.status is TransactionStatus.COMPLETED for item in value.transactions
    )


def test_missing_duplicate_and_inconsistent_quotes_fail() -> None:
    selected = purchase_intent("intent-a")
    context, clock, _ = runtime(intents=(selected,), quotes=())
    with pytest.raises(ValueError, match="one quote per intent"):
        TransactionEngine().execute(context, clock)
    duplicate = quote(selected)
    context, clock, _ = runtime(intents=(selected,), quotes=(duplicate, duplicate))
    with pytest.raises(ValueError, match="Duplicate PriceQuote"):
        TransactionEngine().execute(context, clock)
    inconsistent = replace(duplicate, customer_id="other")
    context, clock, _ = runtime(intents=(selected,), quotes=(inconsistent,))
    with pytest.raises(ValueError, match="does not match"):
        TransactionEngine().execute(context, clock)


@pytest.mark.parametrize(
    "opened_at,active,message",
    [
        (date(2026, 8, 16), True, "unopened Location"),
        (date(2020, 1, 1), False, "unavailable Product"),
    ],
)
def test_upstream_master_data_inconsistency_fails(
    opened_at: date, active: bool, message: str
) -> None:
    context, clock, _ = runtime(opened_at=opened_at, product_active=active)
    with pytest.raises(ValueError, match=message):
        TransactionEngine().execute(context, clock)


def test_empty_context_and_models_are_immutable() -> None:
    value, _, store = result(intents=(), quotes=())
    assert value.transactions == ()
    assert (
        value.completed_count,
        value.rejected_count,
        value.completed_units,
        value.rejected_units,
    ) == (0, 0, 0, 0)
    assert (
        value.gross_amount,
        value.discount_amount,
        value.net_amount,
        value.lost_sales_amount,
    ) == (ZERO_MONEY,) * 4
    assert [event.event_type for event in store.all_events()] == [
        "TransactionContextGenerated"
    ]
    with pytest.raises(FrozenInstanceError):
        value.__setattr__("total_transactions", 1)


@pytest.mark.parametrize(
    "collection_name",
    ["temporal_context", "customer_behavior_context", "pricing_context"],
)
def test_current_tick_contexts_are_required(collection_name: str) -> None:
    context, clock, _ = runtime()
    context.state.collection(collection_name).remove("tick-0")
    with pytest.raises(ValueError, match=f"{collection_name} context is missing"):
        TransactionEngine().execute(context, clock)


def test_save_before_publish_and_duplicate_execution() -> None:
    context, clock, store = runtime()
    observed: list[bool] = []
    for event_type in ("TransactionCompleted", "TransactionContextGenerated"):
        context.event_bus.subscribe(
            event_type,
            lambda event: observed.append(
                context.state.collection("transaction_context").contains("tick-0")
            ),
        )
    engine = TransactionEngine()
    engine.execute(context, clock)
    assert observed == [True, True]
    before = store.count()
    with pytest.raises(ValueError, match="already exists"):
        engine.execute(context, clock)
    assert store.count() == before


def test_three_product_intents_create_one_basket_transaction() -> None:
    intents = tuple(
        purchase_intent(f"intent-{suffix}", 1, product_id=f"product-{suffix}")
        for suffix in ("a", "b", "c")
    )
    context, clock, _ = runtime(intents=intents)
    for suffix in ("b", "c"):
        item = Product(
            f"product-{suffix}",
            suffix.upper(),
            "category-a",
            "COP",
            Decimal("100.00"),
            Decimal("50.00"),
            Decimal("0.5000"),
            1.0,
            True,
        )
        context.state.collection("products").add(item.id, item)
        context.state.collection("inventory").add(
            f"inventory-{suffix}",
            InventoryItem(f"inventory-{suffix}", "location-a", item.id, 5, 0, 10, True),
        )
    TransactionEngine().execute(context, clock)
    value = context.state.collection("transaction_context").require("tick-0")
    assert isinstance(value, TransactionContext)
    assert value.total_transactions == 1
    assert value.transaction_lines == 3
    assert len(value.transactions[0].lines) == 3
    assert value.transactions[0].status is TransactionStatus.COMPLETED


def test_three_rejected_lines_create_one_rejected_basket() -> None:
    intents = tuple(purchase_intent(f"intent-{index}", 1) for index in range(3))
    value, _, _ = result(
        intents=intents,
        inventory=(InventoryItem("i", "location-a", "product-a", 0, 0, 10, True),),
    )
    assert value.total_transactions == 1
    assert value.transaction_lines == value.rejected_lines == 3
    assert value.transactions[0].status is TransactionStatus.REJECTED


def test_same_customer_with_two_baskets_creates_two_transactions() -> None:
    intents = (
        purchase_intent("intent-a", 1, basket_id="basket-a"),
        purchase_intent("intent-b", 1, basket_id="basket-b"),
    )
    value, _, _ = result(intents=intents)
    assert value.total_transactions == 2
    assert [item.basket_id for item in value.transactions] == ["basket-a", "basket-b"]
