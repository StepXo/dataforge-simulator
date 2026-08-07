"""Tests for customer behavior models, weights, and execution."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.customers.models import Customer, CustomerSegment, PreferredChannel
from dataforge.engines.customer_behavior.engine import (
    CustomerBehaviorEngine,
    CustomerBehaviorEngineConfig,
    _customer_weight,
    _promotion_propensity,
    _select_channel,
)
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.models import Location
from dataforge.products.models import Product
from dataforge.promotions.models import PromotionChannel, PromotionTargetType

NOW = datetime(2026, 8, 15, 12)


def location(identifier: str = "location-a", region: str = "region-a") -> Location:
    return Location(
        identifier,
        "A",
        "city-a",
        "area-a",
        region,
        "country-a",
        100,
        1.0,
        date(2020, 1, 1),
    )


def product() -> Product:
    return Product(
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


def customer(
    identifier: str = "customer-000001",
    *,
    segment: CustomerSegment = CustomerSegment.REGULAR,
    active: bool = True,
    registered_at: date = date(2020, 1, 1),
    region: str = "region-a",
    preferred_location: str = "location-a",
    preferred_channel: PreferredChannel = PreferredChannel.MOBILE,
    frequency: float = 2.0,
    activity: float = 1.0,
    sensitivity: float = 1.0,
) -> Customer:
    return Customer(
        identifier,
        "city-a",
        region,
        preferred_location,
        segment,
        frequency,
        preferred_channel,
        sensitivity,
        activity,
        registered_at,
        active,
    )


def promotion(
    channel: PromotionChannel = PromotionChannel.ALL,
    target_type: PromotionTargetType = PromotionTargetType.GLOBAL,
    target_ids: tuple[str, ...] = (),
) -> ActivePromotion:
    return ActivePromotion("promotion-a", target_type, target_ids, channel, 0.1, 0.2)


def runtime(
    *,
    seed: int = 42,
    customers: tuple[Customer, ...] | None = None,
    demand_units: int = 8,
    item_location: Location | None = None,
    promotions: tuple[ActivePromotion, ...] = (),
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        seed,
        DateRange(date(2026, 8, 15), date(2026, 8, 15)),
        RandomEngine(seed),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    selected_location = item_location or location()
    selected_product = product()
    collections = {
        "customers": customers or (customer(),),
        "locations": (selected_location,),
        "products": (selected_product,),
        "temporal_context": (TemporalContext(0, NOW, TickUnit.HOUR),),
        "promotion_context": (PromotionContext(0, NOW, promotions),),
        "demand_context": (
            DemandContext(
                0,
                NOW,
                (
                    DemandRecord(
                        selected_location.id, selected_product.id, 8.0, demand_units
                    ),
                ),
                demand_units,
            ),
        ),
    }
    for name, values in collections.items():
        state_collection = context.state.create_collection(name)
        for index, value in enumerate(values):
            key = (
                "tick-0"
                if name.endswith("_context")
                else getattr(value, "id", str(index))
            )
            state_collection.add(key, value)
    return context, clock, store


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_units_per_intent", 0),
        ("occasional_activity_factor", -0.1),
        ("regular_activity_factor", -0.1),
        ("frequent_activity_factor", -0.1),
        ("preferred_location_bonus", -0.1),
        ("preferred_channel_bonus", -0.1),
        ("promotion_sensitivity_weight", -0.1),
    ],
)
def test_config_rejects_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        CustomerBehaviorEngineConfig.model_validate({field: value})


def test_models_validate_totals_and_are_immutable() -> None:
    intent = PurchaseIntent(
        "intent-15-000001",
        "customer-1",
        "location-a",
        "product-a",
        PreferredChannel.MOBILE,
        2,
        15,
    )
    behavior = CustomerBehaviorContext(15, NOW, (intent,), 1, 2, 3)
    assert behavior.total_requested_units + behavior.unassigned_demand_units == 5
    with pytest.raises(FrozenInstanceError):
        intent.__setattr__("requested_quantity", 3)
    with pytest.raises(ValueError, match="at least one"):
        PurchaseIntent("x", "c", "l", "p", PreferredChannel.PHYSICAL, 0, 0)
    with pytest.raises(ValueError, match="total_intents"):
        CustomerBehaviorContext(0, NOW, (intent,), 0, 2, 0)
    with pytest.raises(ValueError, match="quantity sum"):
        CustomerBehaviorContext(0, NOW, (intent,), 1, 1, 0)
    with pytest.raises(ValueError, match="non-negative"):
        CustomerBehaviorContext(0, NOW, (), 0, 0, -1)


def test_customer_weight_uses_segment_frequency_activity_and_location() -> None:
    config = CustomerBehaviorEngineConfig()
    place = location()
    item = product()
    empty_promotions = PromotionContext(0, NOW, ())
    occasional = _customer_weight(
        customer(segment=CustomerSegment.OCCASIONAL),
        place,
        item,
        empty_promotions,
        config,
    )
    regular = _customer_weight(customer(), place, item, empty_promotions, config)
    frequent = _customer_weight(
        customer(segment=CustomerSegment.FREQUENT),
        place,
        item,
        empty_promotions,
        config,
    )
    assert occasional < regular < frequent
    assert _customer_weight(
        customer(frequency=4.0), place, item, empty_promotions, config
    ) == pytest.approx(regular * 2)
    assert _customer_weight(
        customer(activity=1.5), place, item, empty_promotions, config
    ) == pytest.approx(regular * 1.5)
    assert _customer_weight(
        customer(preferred_location="other"), place, item, empty_promotions, config
    ) == pytest.approx(regular / config.preferred_location_bonus)


def test_promotion_sensitivity_and_channel_specific_influence() -> None:
    config = CustomerBehaviorEngineConfig()
    place = location()
    item = product()
    mobile = PromotionContext(0, NOW, (promotion(PromotionChannel.MOBILE),))
    sensitive = customer(sensitivity=1.0)
    insensitive = customer(sensitivity=0.0)
    assert _promotion_propensity(
        sensitive, place, item, mobile, PromotionChannel.MOBILE, config
    ) > _promotion_propensity(
        insensitive, place, item, mobile, PromotionChannel.MOBILE, config
    )
    assert (
        _promotion_propensity(
            sensitive, place, item, mobile, PromotionChannel.PHYSICAL, config
        )
        == 1.0
    )


@pytest.mark.parametrize(
    "target_type,target_ids,expected",
    [
        (PromotionTargetType.GLOBAL, (), True),
        (PromotionTargetType.REGION, ("region-a",), True),
        (PromotionTargetType.LOCATION, ("location-a",), True),
        (PromotionTargetType.CATEGORY, ("category-a",), True),
        (PromotionTargetType.PRODUCT, ("product-a",), True),
        (PromotionTargetType.PRODUCT, ("other",), False),
    ],
)
def test_promotion_targets_affect_customer_weight(
    target_type: PromotionTargetType,
    target_ids: tuple[str, ...],
    expected: bool,
) -> None:
    config = CustomerBehaviorEngineConfig()
    place = location()
    item = product()
    shopper = customer(sensitivity=1.0)
    baseline = _customer_weight(
        shopper, place, item, PromotionContext(0, NOW, ()), config
    )
    promoted = _customer_weight(
        shopper,
        place,
        item,
        PromotionContext(
            0, NOW, (promotion(target_type=target_type, target_ids=target_ids),)
        ),
        config,
    )
    assert (promoted > baseline) is expected


def test_preferred_channel_has_greater_selection_weight() -> None:
    config = CustomerBehaviorEngineConfig(preferred_channel_bonus=1000)
    chosen = _select_channel(
        customer(preferred_channel=PreferredChannel.MOBILE),
        location(),
        product(),
        PromotionContext(0, NOW, ()),
        config,
        RandomEngine(1),
    )
    assert chosen is PreferredChannel.MOBILE


@pytest.mark.parametrize(
    "candidate",
    [
        customer(active=False),
        customer(segment=CustomerSegment.INACTIVE),
        customer(registered_at=date(2026, 8, 16)),
        customer(region="region-b"),
    ],
)
def test_ineligible_customer_leaves_demand_unassigned(candidate: Customer) -> None:
    context, clock, _ = runtime(customers=(candidate,), demand_units=5)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents == ()
    assert result.total_requested_units == 0
    assert result.unassigned_demand_units == 5


def test_assignment_conserves_units_limits_quantities_and_publishes_after_save() -> (
    None
):
    context, clock, store = runtime(demand_units=11)
    observed: list[bool] = []
    context.event_bus.subscribe(
        "CustomerBehaviorContextGenerated",
        lambda event: observed.append(
            context.state.collection("customer_behavior_context").contains("tick-0")
        ),
    )
    CustomerBehaviorEngine(
        CustomerBehaviorEngineConfig(max_units_per_intent=3)
    ).execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.total_requested_units + result.unassigned_demand_units == 11
    assert result.total_intents == len(result.intents)
    assert all(1 <= intent.requested_quantity <= 3 for intent in result.intents)
    assert [intent.id for intent in result.intents] == [
        f"intent-0-{index:06d}" for index in range(1, len(result.intents) + 1)
    ]
    assert observed == [True]
    event = store.all_events()[-1]
    assert event.event_type == "CustomerBehaviorContextGenerated"
    assert event.payload["total_requested_units"] == 11


def test_zero_demand_creates_context_without_intents() -> None:
    context, clock, _ = runtime(demand_units=0)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents == ()
    assert result.unassigned_demand_units == 0


def test_same_seed_produces_identical_intents() -> None:
    first_context, first_clock, _ = runtime(seed=7, demand_units=20)
    second_context, second_clock, _ = runtime(seed=7, demand_units=20)
    CustomerBehaviorEngine().execute(first_context, first_clock)
    CustomerBehaviorEngine().execute(second_context, second_clock)
    assert first_context.state.collection("customer_behavior_context").all() == (
        second_context.state.collection("customer_behavior_context").all()
    )


def test_different_seed_can_change_assignment() -> None:
    shoppers = (
        customer("customer-000001"),
        customer("customer-000002", preferred_channel=PreferredChannel.PHYSICAL),
    )
    first_context, first_clock, _ = runtime(seed=1, customers=shoppers, demand_units=20)
    second_context, second_clock, _ = runtime(
        seed=2, customers=shoppers, demand_units=20
    )
    CustomerBehaviorEngine().execute(first_context, first_clock)
    CustomerBehaviorEngine().execute(second_context, second_clock)
    assert first_context.state.collection("customer_behavior_context").all() != (
        second_context.state.collection("customer_behavior_context").all()
    )


def test_duplicate_execution_fails_without_second_event() -> None:
    context, clock, store = runtime()
    engine = CustomerBehaviorEngine()
    engine.execute(context, clock)
    event_count = store.count()
    with pytest.raises(ValueError, match="already exists"):
        engine.execute(context, clock)
    assert store.count() == event_count
