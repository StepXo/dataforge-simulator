"""Tests for fail-fast state validation."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.customers.models import Customer, CustomerSegment, PreferredChannel
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext
from dataforge.engines.inventory.models import InventoryContext
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.pricing.models import PricingContext
from dataforge.engines.replenishment.models import ReplenishmentContext
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import TransactionContext
from dataforge.engines.validation.engine import StateValidationEngine
from dataforge.engines.validation.models import ValidationContext
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.models import City, Location
from dataforge.inventory.models import InventoryItem
from dataforge.products.models import Product

NOW = datetime(2026, 8, 15, 12)
ZERO = Decimal("0.00")
MASTER_NAMES = (
    "countries",
    "regions",
    "administrative_areas",
    "cities",
    "locations",
    "categories",
    "products",
    "customers",
    "inventory",
    "pending_replenishments",
)


def zero_metrics() -> MetricsContext:
    return MetricsContext(
        0,
        NOW,
        0,
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
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def runtime() -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        1,
        DateRange(date(2026, 8, 15), date(2026, 8, 15)),
        RandomEngine(1),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    for name in MASTER_NAMES:
        context.state.create_collection(name)
    values = {
        "temporal_context": TemporalContext(0, NOW, TickUnit.HOUR),
        "demand_context": DemandContext(0, NOW, (), 0),
        "customer_behavior_context": CustomerBehaviorContext(0, NOW, (), 0, 0, 0),
        "pricing_context": PricingContext(0, NOW, None, (), ZERO, ZERO, ZERO),
        "transaction_context": TransactionContext(
            0, NOW, (), 0, 0, 0, 0, ZERO, ZERO, ZERO, ZERO
        ),
        "inventory_context": InventoryContext(0, NOW, (), (), (), 0, 0),
        "replenishment_context": ReplenishmentContext(0, NOW, (), (), (), 0, 0, 0),
        "metrics_context": zero_metrics(),
    }
    for name, value in values.items():
        collection = context.state.create_collection(name)
        collection.add("tick-0", value)
    return context, clock, store


def test_valid_empty_tick_creates_immutable_context_and_event() -> None:
    context, clock, store = runtime()
    before_names = context.state.collection_names()
    StateValidationEngine().execute(context, clock)
    value = context.state.collection("validation_context").require("tick-0")
    assert value == ValidationContext(0, NOW, 13, 18, True)
    assert context.state.collection_names() == (*before_names, "validation_context")
    assert store.all_events()[0].event_type == "StateValidationCompleted"
    with pytest.raises(FrozenInstanceError):
        value.__setattr__("valid", False)


def test_duplicate_execution_fails_without_second_event() -> None:
    context, clock, store = runtime()
    engine = StateValidationEngine()
    engine.execute(context, clock)
    with pytest.raises(ValueError, match="already executed"):
        engine.execute(context, clock)
    assert store.count() == 1


def test_missing_context_fails_without_success_result() -> None:
    context, clock, store = runtime()
    context.state.collection("metrics_context").remove("tick-0")
    with pytest.raises(ValueError, match="metrics_context context is missing"):
        StateValidationEngine().execute(context, clock)
    assert context.state.collection("validation_context").count() == 0
    assert store.count() == 0


def test_geography_corruption_is_detected() -> None:
    data = {name: () for name in MASTER_NAMES}
    data["cities"] = (City("city-x", "X", "area-x", "region-x", "country-x"),)
    with pytest.raises(ValueError, match="missing administrative area"):
        StateValidationEngine()._validate_geography(data)


def test_negative_stock_and_duplicate_assortment_are_detected() -> None:
    place = Location(
        "location-a",
        "A",
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        10,
        1.0,
        date(2020, 1, 1),
    )
    product = Product(
        "product-a",
        "A",
        "category-a",
        "COP",
        Decimal("10"),
        Decimal("5"),
        Decimal("0.5"),
        1.0,
        True,
    )
    base = {name: () for name in MASTER_NAMES}
    base["locations"] = (place,)
    base["products"] = (product,)
    base["inventory"] = (
        InventoryItem("inventory-a", place.id, product.id, -1, 0, 10, True),
    )
    with pytest.raises(ValueError, match="negative stock"):
        StateValidationEngine()._validate_inventory(base)
    base["inventory"] = (
        InventoryItem("inventory-a", place.id, product.id, 1, 0, 10, True),
        InventoryItem("inventory-b", place.id, product.id, 1, 0, 10, True),
    )
    with pytest.raises(ValueError, match="Duplicate inventory assortment"):
        StateValidationEngine()._validate_inventory(base)


def test_basket_inconsistency_and_metrics_mismatch_are_detected() -> None:
    place = Location(
        "location-a",
        "A",
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        10,
        1.0,
        date(2020, 1, 1),
    )
    product = Product(
        "product-a",
        "A",
        "category-a",
        "COP",
        Decimal("10"),
        Decimal("5"),
        Decimal("0.5"),
        1.0,
        True,
    )
    customers = tuple(
        Customer(
            f"customer-{index}",
            "city-a",
            "region-a",
            place.id,
            CustomerSegment.REGULAR,
            1.0,
            PreferredChannel.MOBILE,
            0.5,
            1.0,
            date(2020, 1, 1),
            True,
        )
        for index in (1, 2)
    )
    intents = tuple(
        PurchaseIntent(
            f"intent-{index}",
            "basket-a",
            customer.id,
            place.id,
            product.id,
            PreferredChannel.MOBILE,
            1,
            0,
        )
        for index, customer in enumerate(customers, start=1)
    )
    behavior = CustomerBehaviorContext(0, NOW, intents, 2, 2, 0)
    data = {name: () for name in MASTER_NAMES}
    data["customers"], data["locations"], data["products"] = (
        customers,
        (place,),
        (product,),
    )
    assortment = {
        (place.id, product.id): InventoryItem(
            "inventory-a", place.id, product.id, 1, 0, 10, True
        )
    }
    with pytest.raises(ValueError, match="Basket"):
        StateValidationEngine()._validate_behavior(
            behavior, TemporalContext(0, NOW, TickUnit.HOUR), data, assortment, 0
        )

    context, clock, _ = runtime()
    context.state.collection("metrics_context").replace(
        "tick-0", replace(zero_metrics(), completed_units=1)
    )
    with pytest.raises(ValueError, match="MetricsContext"):
        StateValidationEngine().execute(context, clock)
