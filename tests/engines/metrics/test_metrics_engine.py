"""Tests for read-only per-tick metrics aggregation."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    InventoryMovementType,
    OutOfStockSignal,
    ReorderSignal,
)
from dataforge.engines.metrics.engine import MetricsEngine
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.pricing.models import PriceQuote, PricingContext
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
    ReplenishmentStatus,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import (
    RejectionReason,
    Transaction,
    TransactionContext,
    TransactionLine,
    TransactionLineStatus,
    TransactionStatus,
)
from dataforge.generators.customers.models import PreferredChannel

NOW = datetime(2026, 8, 15, 12)
ZERO = Decimal("0.00")


def transaction(identifier: str, quantity: int, completed: bool) -> Transaction:
    gross = Decimal("100.00") if completed else Decimal("200.00")
    discount = Decimal("20.00") if completed else ZERO
    net = Decimal("80.00") if completed else Decimal("200.00")
    line_status = (
        TransactionLineStatus.COMPLETED if completed else TransactionLineStatus.REJECTED
    )
    line = TransactionLine(
        f"line-{identifier}",
        f"intent-{identifier}",
        f"intent-{identifier}",
        "product-a",
        quantity,
        gross / Decimal(quantity),
        gross,
        discount,
        net,
        (),
        line_status,
        None if completed else RejectionReason.INSUFFICIENT_STOCK,
    )
    return Transaction(
        identifier,
        f"basket-{identifier}",
        "customer-a",
        "location-a",
        PreferredChannel.MOBILE,
        (line,),
        "COP",
        gross if completed else ZERO,
        discount if completed else ZERO,
        net if completed else ZERO,
        net if not completed else ZERO,
        quantity if completed else 0,
        quantity if not completed else 0,
        TransactionStatus.COMPLETED if completed else TransactionStatus.REJECTED,
        0,
        NOW,
    )


def contexts(*, unassigned: int = 20, inventory_units: int = 60) -> dict[str, object]:
    intent = PurchaseIntent(
        "intent-a",
        "basket-0-000001",
        "customer-a",
        "location-a",
        "product-a",
        PreferredChannel.MOBILE,
        80,
        0,
    )
    quote = PriceQuote(
        intent.id,
        intent.basket_id,
        intent.customer_id,
        intent.location_id,
        intent.product_id,
        intent.channel,
        80,
        "COP",
        Decimal("1.00"),
        Decimal("0.25"),
        Decimal("0.75"),
        Decimal("80.00"),
        Decimal("20.00"),
        Decimal("60.00"),
        (),
        0,
    )
    completed = transaction("transaction-a", 60, True)
    rejected = transaction("transaction-b", 20, False)
    sale = InventoryMovement(
        "movement-a",
        "inventory-a",
        "location-a",
        "product-a",
        completed.id,
        completed.basket_id,
        InventoryMovementType.SALE,
        inventory_units,
        100,
        100 - inventory_units,
        0,
        NOW,
    )
    pending = PendingReplenishment(
        "replenishment-a",
        "inventory-a",
        "location-a",
        "product-a",
        92,
        0,
        1,
        NOW,
        ReplenishmentStatus.PENDING,
    )
    return {
        "temporal_context": TemporalContext(0, NOW, TickUnit.HOUR),
        "demand_context": DemandContext(
            0, NOW, (DemandRecord("location-a", "product-a", 100.0, 100),), 100
        ),
        "customer_behavior_context": CustomerBehaviorContext(
            0, NOW, (intent,), 1, 80, unassigned
        ),
        "pricing_context": PricingContext(
            0,
            NOW,
            "COP",
            (quote,),
            Decimal("80.00"),
            Decimal("20.00"),
            Decimal("60.00"),
        ),
        "transaction_context": TransactionContext(
            0,
            NOW,
            (completed, rejected),
            2,
            1,
            0,
            1,
            2,
            1,
            1,
            60,
            20,
            Decimal("100.00"),
            Decimal("20.00"),
            Decimal("80.00"),
            Decimal("200.00"),
        ),
        "inventory_context": InventoryContext(
            0,
            NOW,
            (sale,),
            (ReorderSignal("inventory-a", "location-a", "product-a", 40, 50, 100, 0),),
            (OutOfStockSignal("other", "location-a", "product-b", 0),),
            inventory_units,
            1,
        ),
        "replenishment_context": ReplenishmentContext(
            0, NOW, (pending,), (), (), 1, 0, 0
        ),
    }


def runtime(
    values: dict[str, object] | None = None,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        1,
        DateRange(date(2026, 8, 15), date(2026, 8, 15)),
        RandomEngine(1),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    for name, value in (values or contexts()).items():
        collection = context.state.create_collection(name)
        collection.add("tick-0", value)
    return context, clock, store


def test_happy_path_copies_official_metrics_and_event_payload() -> None:
    context, clock, store = runtime()
    MetricsEngine().execute(context, clock)
    value = context.state.collection("metrics_context").require("tick-0")
    assert isinstance(value, MetricsContext)
    assert (value.demand_records, value.demand_units) == (1, 100)
    assert (
        value.purchase_intents,
        value.intent_units,
        value.unassigned_demand_units,
    ) == (1, 80, 20)
    assert (
        value.total_transactions,
        value.completed_transactions,
        value.partially_completed_transactions,
        value.rejected_transactions,
    ) == (2, 1, 0, 1)
    assert (value.transaction_lines, value.completed_lines, value.rejected_lines) == (
        2,
        1,
        1,
    )
    assert (value.completed_units, value.rejected_units) == (60, 20)
    assert (
        value.gross_sales_amount,
        value.discount_amount,
        value.net_sales_amount,
    ) == (Decimal("100.00"), Decimal("20.00"), Decimal("80.00"))
    assert value.lost_sales_amount == Decimal("200.00")
    assert (value.inventory_movements, value.units_removed_from_inventory) == (1, 60)
    assert (value.reorder_signals, value.out_of_stock_signals) == (1, 1)
    assert (
        value.replenishments_scheduled,
        value.replenishments_completed,
        value.units_replenished,
    ) == (1, 0, 0)
    assert store.all_events()[0].payload["net_sales_amount"] == "80.00"
    assert store.all_events()[0].payload["lost_sales_amount"] == "200.00"


def test_metrics_context_is_immutable_and_keeps_decimal() -> None:
    context, clock, _ = runtime()
    MetricsEngine().execute(context, clock)
    value = context.state.collection("metrics_context").require("tick-0")
    assert isinstance(value.net_sales_amount, Decimal)
    with pytest.raises(FrozenInstanceError):
        value.__setattr__("demand_units", 0)


def test_demand_conservation_is_checked() -> None:
    context, clock, store = runtime(contexts(unassigned=10))
    with pytest.raises(ValueError, match="equal demand units"):
        MetricsEngine().execute(context, clock)
    assert store.count() == 0


def test_inventory_units_must_equal_completed_units() -> None:
    context, clock, store = runtime(contexts(inventory_units=59))
    with pytest.raises(ValueError, match="equal completed units"):
        MetricsEngine().execute(context, clock)
    assert store.count() == 0


def test_empty_tick_and_duplicate_execution() -> None:
    values = {
        "temporal_context": TemporalContext(0, NOW, TickUnit.HOUR),
        "demand_context": DemandContext(0, NOW, (), 0),
        "customer_behavior_context": CustomerBehaviorContext(0, NOW, (), 0, 0, 0),
        "pricing_context": PricingContext(0, NOW, None, (), ZERO, ZERO, ZERO),
        "transaction_context": TransactionContext(
            0,
            NOW,
            (),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            ZERO,
            ZERO,
            ZERO,
            ZERO,
        ),
        "inventory_context": InventoryContext(0, NOW, (), (), (), 0, 0),
        "replenishment_context": ReplenishmentContext(0, NOW, (), (), (), 0, 0, 0),
    }
    context, clock, store = runtime(values)
    engine = MetricsEngine()
    engine.execute(context, clock)
    value = context.state.collection("metrics_context").require("tick-0")
    assert value.demand_units == value.net_sales_amount == 0
    before = store.count()
    with pytest.raises(ValueError, match="already exists"):
        engine.execute(context, clock)
    assert store.count() == before


@pytest.mark.parametrize("missing", list(contexts()))
def test_all_tick_contexts_are_required(missing: str) -> None:
    values = contexts()
    values.pop(missing)
    context, clock, _ = runtime(values)
    with pytest.raises(ValueError, match="missing"):
        MetricsEngine().execute(context, clock)
