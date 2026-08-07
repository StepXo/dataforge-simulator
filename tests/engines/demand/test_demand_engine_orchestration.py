"""Integration tests for the demand engine pipeline."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.demand.engine import DemandEngine
from dataforge.engines.promotion.engine import PromotionEngine
from dataforge.engines.time.engine import TimeEngine
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.models import Location
from dataforge.inventory.models import InventoryItem
from dataforge.products.models import Product
from dataforge.promotions.models import Promotion, PromotionChannel, PromotionTargetType
from dataforge.simulation.orchestrator import SimulationOrchestrator


def runtime() -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        42,
        DateRange(date(2026, 8, 10), date(2026, 8, 10)),
        RandomEngine(42),
        EventBus(store),
    )
    clock = SimulationClock(
        TimeRange(datetime(2026, 8, 10, 8), datetime(2026, 8, 10, 10)), TickUnit.HOUR
    )
    item_location = Location(
        "location-a",
        "A",
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        100,
        1.0,
        date(2020, 1, 1),
    )
    item_product = Product(
        "product-a",
        "A",
        "category-a",
        "COP",
        Decimal("100"),
        Decimal("50"),
        Decimal("0.5000"),
        1.0,
        True,
    )
    context.state.create_collection("locations").add(item_location.id, item_location)
    context.state.create_collection("products").add(item_product.id, item_product)
    context.state.create_collection("inventory").add(
        "inventory-a",
        InventoryItem("inventory-a", item_location.id, item_product.id, 0, 0, 10, True),
    )
    context.state.create_collection("promotions").add(
        "promotion-a",
        Promotion(
            "promotion-a",
            "A",
            date(2026, 8, 10),
            date(2026, 8, 10),
            PromotionTargetType.GLOBAL,
            (),
            PromotionChannel.ALL,
            0.1,
            0.2,
            True,
        ),
    )
    return context, clock, store


def test_time_promotion_demand_pipeline_preserves_history() -> None:
    context, clock, store = runtime()
    summary = SimulationOrchestrator(
        [TimeEngine(), PromotionEngine(), DemandEngine()]
    ).run(context, clock)
    assert summary.ticks_processed == 3
    assert summary.engine_executions == 9
    for name in ("temporal_context", "promotion_context", "demand_context"):
        collection = context.state.collection(name)
        assert tuple(collection.contains(f"tick-{index}") for index in range(3)) == (
            True,
            True,
            True,
        )
    assert (
        sum(
            event.event_type == "DemandContextGenerated" for event in store.all_events()
        )
        == 3
    )


@pytest.mark.parametrize(
    "engines,missing",
    [
        ([DemandEngine(), TimeEngine(), PromotionEngine()], "temporal_context"),
        ([TimeEngine(), DemandEngine(), PromotionEngine()], "promotion_context"),
    ],
)
def test_wrong_order_fails(engines: list[object], missing: str) -> None:
    context, clock, _ = runtime()
    with pytest.raises(ValueError, match=f"missing: {missing}"):
        SimulationOrchestrator(engines).run(context, clock)
    assert clock.tick_index == 0
