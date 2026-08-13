"""Tests for customer behavior models, weights, and execution."""

from collections import Counter
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.customer_behavior.engine import (
    CustomerBehaviorEngine,
    CustomerBehaviorEngineConfig,
    _build_intents,
    _customer_weight,
    _DemandPool,
    _IntentDraft,
    _is_temporally_available,
    _promotion_propensity,
    _select_channel,
    activity_probability,
)
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.generators.customers.models import (
    Customer,
    CustomerSegment,
    PreferredChannel,
)
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionChannel, PromotionTargetType

NOW = datetime(2026, 8, 15, 12)


def location(
    identifier: str = "location-a",
    region: str = "region-a",
    city: str = "city-a",
    opened_at: date = date(2020, 1, 1),
) -> Location:
    return Location(
        identifier,
        "A",
        city,
        "area-a",
        region,
        "country-a",
        100,
        1.0,
        opened_at,
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
    home_city: str = "city-a",
    preferred_location: str = "location-a",
    preferred_channel: PreferredChannel = PreferredChannel.MOBILE,
    frequency: float = 1_000_000.0,
    activity: float = 1.0,
    sensitivity: float = 1.0,
) -> Customer:
    return Customer(
        identifier,
        home_city,
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
    extra_locations: tuple[Location, ...] = (),
    inventory_items: tuple[InventoryItem, ...] | None = None,
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
    selected_inventory = inventory_items or (
        InventoryItem(
            "inventory-a",
            selected_location.id,
            selected_product.id,
            0,
            0,
            10,
            True,
        ),
    )
    collections = {
        "customers": customers or (customer(),),
        "locations": (selected_location, *extra_locations),
        "products": (selected_product,),
        "inventory": selected_inventory,
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
        "basket-15-000001",
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
        PurchaseIntent("x", "b", "c", "l", "p", PreferredChannel.PHYSICAL, 0, 0)
    with pytest.raises(ValueError, match="total_intents"):
        CustomerBehaviorContext(0, NOW, (intent,), 0, 2, 0)
    with pytest.raises(ValueError, match="quantity sum"):
        CustomerBehaviorContext(0, NOW, (intent,), 1, 1, 0)
    with pytest.raises(ValueError, match="non-negative"):
        CustomerBehaviorContext(0, NOW, (), 0, 0, -1)


def test_basket_grouping_is_deterministic_and_uses_customer_location_channel() -> None:
    drafts = [
        _IntentDraft(
            "customer-a", "location-a", "product-a", PreferredChannel.MOBILE, 2
        ),
        _IntentDraft(
            "customer-a", "location-a", "product-b", PreferredChannel.MOBILE, 1
        ),
        _IntentDraft(
            "customer-b", "location-a", "product-a", PreferredChannel.MOBILE, 1
        ),
        _IntentDraft(
            "customer-a", "location-b", "product-a", PreferredChannel.MOBILE, 1
        ),
        _IntentDraft(
            "customer-a", "location-a", "product-a", PreferredChannel.PHYSICAL, 1
        ),
    ]
    intents = _build_intents(drafts, tick_index=10, demand_tick_index=10)
    assert [intent.id for intent in intents] == [
        f"intent-10-{index:06d}" for index in range(1, 6)
    ]
    assert [intent.basket_id for intent in intents] == [
        "basket-10-000001",
        "basket-10-000001",
        "basket-10-000002",
        "basket-10-000003",
        "basket-10-000004",
    ]
    assert intents == _build_intents(drafts, tick_index=10, demand_tick_index=10)
    assert _build_intents(drafts, 11, 11)[0].basket_id == "basket-11-000001"


def test_customer_weight_uses_propensity_not_segment_or_monthly_rate() -> None:
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
    assert occasional == regular == frequent
    assert _customer_weight(
        customer(frequency=4.0), place, item, empty_promotions, config
    ) == pytest.approx(regular)
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


def test_configured_preferred_channel_is_used() -> None:
    config = CustomerBehaviorEngineConfig()
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
        customer(frequency=0),
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
    assert event.payload["total_requested_units"] <= 3
    if event.payload["intents"]:
        assert event.payload["intents"][0]["basket_id"].startswith("basket-0-")


def test_monthly_rate_probability_scales_with_tick_duration_and_rate() -> None:
    hour = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    day = SimulationClock(TimeRange(NOW, NOW), TickUnit.DAY)
    assert activity_probability(0, hour) == 0
    assert activity_probability(20, hour) < activity_probability(20, day)
    assert activity_probability(10, hour) < activity_probability(20, hour)


def test_hourly_availability_observations_match_monthly_rate_scale() -> None:
    clock = SimulationClock(
        TimeRange(datetime(2024, 1, 1), datetime(2024, 1, 31, 23)),
        TickUnit.HOUR,
    )
    random_engine = RandomEngine(42)
    shoppers = tuple(
        customer(f"customer-{index:06d}", frequency=20) for index in range(200)
    )
    observed = 0
    while not clock.is_finished:
        observed += sum(
            _is_temporally_available(shopper, clock, random_engine)
            for shopper in shoppers
        )
        clock.advance()
    assert observed / len(shoppers) == pytest.approx(20, rel=0.10)


def test_customer_creates_at_most_one_basket_and_excess_is_unassigned() -> None:
    context, clock, _ = runtime(customers=(customer(),), demand_units=20)
    CustomerBehaviorEngine(
        CustomerBehaviorEngineConfig(max_units_per_intent=4)
    ).execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert len({intent.basket_id for intent in result.intents}) <= 1
    assert result.total_requested_units <= 4
    assert result.total_requested_units + result.unassigned_demand_units == 20


def test_available_customer_can_receive_multiple_products_in_one_basket() -> None:
    engine = CustomerBehaviorEngine()
    shopper = customer()
    place = location()
    promotions = PromotionContext(0, NOW, ())
    drafts: list[_IntentDraft] = []
    assigned_products: set[tuple[str, str]] = set()
    first = product()
    second = Product(
        "product-b",
        "B",
        "category-a",
        "COP",
        Decimal("80"),
        Decimal("40"),
        Decimal("0.5000"),
        1.0,
        True,
    )
    pools = [_DemandPool(place, first, 1), _DemandPool(place, second, 1)]
    baskets: dict[str, tuple[str, PreferredChannel]] = {}
    engine._allocate_new_baskets(
        [shopper],
        pools,
        promotions,
        RandomEngine(42),
        drafts,
        baskets,
        assigned_products,
    )
    engine._fill_existing_baskets(
        [shopper],
        pools,
        promotions,
        RandomEngine(42),
        drafts,
        baskets,
        assigned_products,
    )
    intents = _build_intents(drafts, 0, 0)
    assert len(intents) == 2
    assert len({intent.basket_id for intent in intents}) == 1


def _two_location_assignment(
    demand_order: tuple[str, str], seed: int = 42
) -> CustomerBehaviorContext:
    first = location("location-a", city="city-a")
    second = location("location-b", city="city-a")
    shoppers = tuple(
        customer(
            f"customer-{index:06d}",
            preferred_location="location-a" if index % 2 else "location-b",
        )
        for index in range(1, 41)
    )
    inventory = (
        InventoryItem("inventory-a", first.id, "product-a", 0, 0, 100, True),
        InventoryItem("inventory-b", second.id, "product-a", 0, 0, 100, True),
    )
    context, clock, _ = runtime(
        seed=seed,
        customers=shoppers,
        item_location=first,
        extra_locations=(second,),
        inventory_items=inventory,
        demand_units=0,
    )
    demand_collection = context.state.collection("demand_context")
    demand_collection.clear()
    records = tuple(
        DemandRecord(location_id, "product-a", 20.0, 20) for location_id in demand_order
    )
    demand_collection.add("tick-0", DemandContext(0, NOW, records, 40))
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    return result


def test_location_assignment_is_independent_of_demand_record_order() -> None:
    forward = _two_location_assignment(("location-a", "location-b"))
    reversed_result = _two_location_assignment(("location-b", "location-a"))
    assert forward == reversed_result
    counts = Counter(intent.location_id for intent in forward.intents)
    assert counts["location-a"] > 0
    assert counts["location-b"] > 0


def test_preferred_location_influences_competitive_assignment() -> None:
    result = _two_location_assignment(("location-a", "location-b"))
    preferred = {
        f"customer-{index:06d}": "location-a" if index % 2 else "location-b"
        for index in range(1, 41)
    }
    matching = sum(
        preferred[intent.customer_id] == intent.location_id for intent in result.intents
    )
    assert matching > len(result.intents) / 2


@pytest.mark.parametrize(
    "channel", (PreferredChannel.PHYSICAL, PreferredChannel.MOBILE)
)
def test_same_region_different_city_is_not_eligible(
    channel: PreferredChannel,
) -> None:
    medellin = location("location-medellin", region="region-andean", city="medellin")
    bogota_customer = customer(
        region="region-andean",
        home_city="bogota",
        preferred_location="location-medellin",
        preferred_channel=channel,
    )
    context, clock, _ = runtime(
        customers=(bogota_customer,), item_location=medellin, demand_units=5
    )
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents == ()
    assert result.unassigned_demand_units == 5


@pytest.mark.parametrize(
    "item",
    [
        InventoryItem(
            "inventory-other", "location-other", "product-a", 10, 0, 20, True
        ),
        InventoryItem(
            "inventory-inactive", "location-a", "product-a", 10, 0, 20, False
        ),
    ],
)
def test_product_not_offered_leaves_demand_unassigned(item: InventoryItem) -> None:
    context, clock, _ = runtime(inventory_items=(item,), demand_units=4)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents == ()
    assert result.unassigned_demand_units == 4


def test_out_of_stock_assortment_still_allows_intent() -> None:
    context, clock, _ = runtime(demand_units=4)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.total_requested_units > 0
    assert result.total_requested_units + result.unassigned_demand_units == 4
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 0
    )


@pytest.mark.parametrize(
    "preferred_opened_at,channel",
    [
        (date(2020, 1, 1), PreferredChannel.MOBILE),
        (date(2026, 8, 16), PreferredChannel.PHYSICAL),
    ],
)
def test_invalid_preferred_location_falls_back_within_same_city(
    preferred_opened_at: date,
    channel: PreferredChannel,
) -> None:
    fallback = location("location-medellin-south", city="medellin")
    preferred = location(
        "location-medellin-center",
        city="medellin",
        opened_at=preferred_opened_at,
    )
    shopper = customer(
        home_city="medellin",
        preferred_location=preferred.id,
        preferred_channel=channel,
    )
    assortment = InventoryItem(
        "inventory-fallback", fallback.id, "product-a", 0, 0, 10, True
    )
    context, clock, _ = runtime(
        customers=(shopper,),
        item_location=fallback,
        extra_locations=(preferred,),
        inventory_items=(assortment,),
        demand_units=3,
    )
    CustomerBehaviorEngine(
        CustomerBehaviorEngineConfig(preferred_channel_bonus=1_000_000)
    ).execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents
    assert all(intent.location_id == fallback.id for intent in result.intents)
    assert all(intent.channel is channel for intent in result.intents)


def test_future_demand_location_is_not_assigned() -> None:
    future = location("location-future", opened_at=date(2026, 8, 16))
    context, clock, _ = runtime(item_location=future, demand_units=6)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    assert result.intents == ()
    assert result.unassigned_demand_units == 6


def test_generated_intents_satisfy_commercial_invariants() -> None:
    shopper = customer(home_city="city-a", region="region-a")
    context, clock, _ = runtime(customers=(shopper,), demand_units=7)
    CustomerBehaviorEngine().execute(context, clock)
    result = context.state.collection("customer_behavior_context").require("tick-0")
    assert isinstance(result, CustomerBehaviorContext)
    locations = {item.id: item for item in context.state.collection("locations").all()}
    customers = {item.id: item for item in context.state.collection("customers").all()}
    inventory = context.state.collection("inventory").all()
    for intent in result.intents:
        selected_location = locations[intent.location_id]
        selected_customer = customers[intent.customer_id]
        assert isinstance(selected_location, Location)
        assert isinstance(selected_customer, Customer)
        assert selected_location.opened_at <= NOW.date()
        assert selected_location.city_id == selected_customer.home_city_id
        assert selected_location.region_id == selected_customer.home_region_id
        assert any(
            isinstance(item, InventoryItem)
            and item.active
            and item.location_id == intent.location_id
            and item.product_id == intent.product_id
            for item in inventory
        )


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
