"""Unit tests for aggregate demand generation."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dataforge.core.engine import SimulationEngine
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.demand.engine import (
    DemandEngine,
    DemandEngineConfig,
    _expected_demand,
    _promotion_factor,
    _stochastic_round,
    _temporal_factor,
)
from dataforge.engines.demand.events import DemandContextGenerated
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.events.event import DomainEvent
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.models import Location
from dataforge.inventory.models import InventoryItem
from dataforge.products.models import Product
from dataforge.promotions.models import PromotionChannel, PromotionTargetType


def location(
    identifier: str = "location-a",
    activity: float = 1.5,
    opened_at: date = date(2020, 1, 1),
) -> Location:
    return Location(
        identifier,
        identifier,
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        100,
        activity,
        opened_at,
    )


def product(
    identifier: str = "product-a", activity: float = 1.2, active: bool = True
) -> Product:
    return Product(
        identifier,
        identifier,
        "category-a",
        "COP",
        Decimal("100"),
        Decimal("50"),
        Decimal("0.5000"),
        activity,
        active,
    )


def runtime(
    current_time: datetime = datetime(2026, 8, 15, 12),
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        42,
        DateRange(current_time.date(), current_time.date()),
        RandomEngine(42),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(current_time, current_time), TickUnit.HOUR)
    return context, clock, store


def prepare_state(
    context: SimulationContext,
    temporal: TemporalContext,
    promotion: PromotionContext,
    *,
    inventory_active: bool = True,
    product_active: bool = True,
    stock: int = 10,
    opened_at: date = date(2020, 1, 1),
) -> None:
    item_location = location(opened_at=opened_at)
    item_product = product(active=product_active)
    context.state.create_collection("locations").add(item_location.id, item_location)
    context.state.create_collection("products").add(item_product.id, item_product)
    context.state.create_collection("inventory").add(
        "inventory-a",
        InventoryItem(
            "inventory-a",
            item_location.id,
            item_product.id,
            stock,
            5,
            20,
            inventory_active,
        ),
    )
    context.state.create_collection("temporal_context").add("tick-0", temporal)
    context.state.create_collection("promotion_context").add("tick-0", promotion)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_demand_min": -1},
        {"base_demand_min": 2, "base_demand_max": 1},
        {"weekend_factor": -1},
        {"mid_month_factor": -1},
        {"month_end_factor": -1},
        {"early_morning_factor": -1},
        {"morning_factor": -1},
        {"lunch_factor": -1},
        {"afternoon_factor": -1},
        {"evening_factor": -1},
        {"night_factor": -1},
        {"max_requested_units_per_item": 0},
    ],
)
def test_demand_engine_config_validation(kwargs: dict[str, int | float]) -> None:
    with pytest.raises(ValidationError):
        DemandEngineConfig(**kwargs)


def test_demand_models_validate_totals_and_are_immutable() -> None:
    record = DemandRecord("location-a", "product-a", 4.25, 4)
    context = DemandContext(0, datetime(2026, 8, 15, 12), (record,), 4)
    assert context.demands == (record,) and context.total_requested_units == 4
    with pytest.raises(ValueError, match="expected_demand"):
        DemandRecord("a", "b", -1, 0)
    with pytest.raises(ValueError, match="requested_units"):
        DemandRecord("a", "b", 1, -1)
    with pytest.raises(ValueError, match="record sum"):
        DemandContext(0, datetime(2026, 8, 15), (record,), 5)
    with pytest.raises(FrozenInstanceError):
        record.__setattr__("requested_units", 9)
    with pytest.raises(FrozenInstanceError):
        context.__setattr__("tick_index", 1)


def test_expected_demand_formula() -> None:
    assert _expected_demand(2, 1.5, 1.2, 2, 1.1) == 7.92


def test_temporal_factors_accumulate() -> None:
    config = DemandEngineConfig()
    morning = TemporalContext(0, datetime(2026, 8, 14, 8), TickUnit.HOUR)
    lunch = TemporalContext(0, datetime(2026, 8, 14, 12), TickUnit.HOUR)
    weekend_mid_month = TemporalContext(0, datetime(2026, 8, 15, 12), TickUnit.HOUR)
    month_end = TemporalContext(0, datetime(2026, 8, 31, 12), TickUnit.HOUR)
    assert _temporal_factor(lunch, config) > _temporal_factor(morning, config)
    assert _temporal_factor(weekend_mid_month, config) == pytest.approx(
        config.lunch_factor * config.weekend_factor * config.mid_month_factor
    )
    assert _temporal_factor(month_end, config) == pytest.approx(
        config.lunch_factor * config.month_end_factor
    )


@pytest.mark.parametrize(
    "target_type,target_ids,expected",
    [
        (PromotionTargetType.GLOBAL, (), 1.2),
        (PromotionTargetType.REGION, ("region-a",), 1.2),
        (PromotionTargetType.LOCATION, ("location-a",), 1.2),
        (PromotionTargetType.CATEGORY, ("category-a",), 1.2),
        (PromotionTargetType.PRODUCT, ("product-a",), 1.2),
        (PromotionTargetType.PRODUCT, ("other",), 1.0),
    ],
)
def test_promotion_targets(
    target_type: PromotionTargetType,
    target_ids: tuple[str, ...],
    expected: float,
) -> None:
    active = ActivePromotion(
        "promotion", target_type, target_ids, PromotionChannel.ALL, 0.1, 0.2
    )
    promotion_context = PromotionContext(0, datetime(2026, 8, 15), (active,))
    assert _promotion_factor(promotion_context, location(), product()) == expected


def test_promotion_factors_multiply_and_channel_specific_promotions_do_not_apply() -> (
    None
):
    promotions = (
        ActivePromotion(
            "a", PromotionTargetType.GLOBAL, (), PromotionChannel.ALL, 0.1, 0.2
        ),
        ActivePromotion(
            "b",
            PromotionTargetType.PRODUCT,
            ("product-a",),
            PromotionChannel.ALL,
            0.1,
            0.1,
        ),
        ActivePromotion(
            "c", PromotionTargetType.GLOBAL, (), PromotionChannel.MOBILE, 0.1, 5.0
        ),
    )
    context = PromotionContext(0, datetime(2026, 8, 15), promotions)
    assert _promotion_factor(context, location(), product()) == pytest.approx(1.2 * 1.1)
    assert (
        _promotion_factor(
            PromotionContext(0, datetime(2026, 8, 15), ()), location(), product()
        )
        == 1.0
    )


def test_stochastic_rounding_is_reproducible() -> None:
    assert _stochastic_round(4.0, RandomEngine(1)) == 4
    assert _stochastic_round(4.25, RandomEngine(1)) == 5
    assert _stochastic_round(4.25, RandomEngine(2)) == 4


@pytest.mark.parametrize(
    "inventory_active,product_active,expected_records",
    [(True, True, 1), (False, True, 0), (True, False, 0)],
)
def test_engine_filters_inactive_items_but_keeps_zero_stock(
    inventory_active: bool,
    product_active: bool,
    expected_records: int,
) -> None:
    context, clock, _ = runtime()
    temporal = TemporalContext(0, clock.current_time, TickUnit.HOUR)
    promotion_context = PromotionContext(0, clock.current_time, ())
    prepare_state(
        context,
        temporal,
        promotion_context,
        inventory_active=inventory_active,
        product_active=product_active,
        stock=0,
    )
    engine: SimulationEngine = DemandEngine()
    engine.execute(context, clock)
    result = context.state.collection("demand_context").require("tick-0")
    assert isinstance(result, DemandContext)
    assert len(result.demands) == expected_records
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 0
    )


def test_future_location_does_not_generate_demand() -> None:
    context, clock, _ = runtime()
    prepare_state(
        context,
        TemporalContext(0, clock.current_time, TickUnit.HOUR),
        PromotionContext(0, clock.current_time, ()),
        opened_at=date(2026, 8, 16),
    )
    DemandEngine().execute(context, clock)
    result = context.state.collection("demand_context").require("tick-0")
    assert isinstance(result, DemandContext)
    assert result.demands == ()
    assert result.total_requested_units == 0


def test_maximum_units_save_before_publish_and_duplicate_execution() -> None:
    context, clock, store = runtime()
    prepare_state(
        context,
        TemporalContext(0, clock.current_time, TickUnit.HOUR),
        PromotionContext(0, clock.current_time, ()),
    )
    observed: list[DomainEvent] = []

    def stored(event: DomainEvent) -> None:
        assert context.state.collection("demand_context").contains("tick-0")
        observed.append(event)

    context.event_bus.subscribe("DemandContextGenerated", stored)
    engine = DemandEngine(
        DemandEngineConfig(
            base_demand_min=100, base_demand_max=100, max_requested_units_per_item=3
        )
    )
    engine.execute(context, clock)
    result = context.state.collection("demand_context").require("tick-0")
    assert isinstance(result, DemandContext)
    assert result.demands[0].expected_demand > 3
    assert result.demands[0].requested_units == 3
    assert len(observed) == 1 and isinstance(observed[0], DemandContextGenerated)
    before = store.count()
    with pytest.raises(ValueError, match="State key already exists: tick-0"):
        engine.execute(context, clock)
    assert store.count() == before
