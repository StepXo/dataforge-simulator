"""Tests for deterministic monetary quote generation."""

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
from dataforge.engines.pricing.engine import PricingEngine
from dataforge.engines.pricing.models import ZERO_MONEY, PriceQuote, PricingContext
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.generators.customers.models import PreferredChannel
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionChannel, PromotionTargetType

NOW = datetime(2026, 8, 15, 12)


def location(
    identifier: str = "location-x", opened: date = date(2020, 1, 1)
) -> Location:
    return Location(
        identifier,
        identifier,
        "city-a",
        "area-a",
        "region-a",
        "country-a",
        100,
        1.0,
        opened,
    )


def product(
    identifier: str = "product-a",
    *,
    price: Decimal = Decimal("100.00"),
    currency: str = "COP",
    active: bool = True,
) -> Product:
    return Product(
        identifier,
        identifier,
        "category-a",
        currency,
        price,
        Decimal("50.00"),
        Decimal("0.5000"),
        1.0,
        active,
    )


def intent(
    identifier: str = "intent-0-000001",
    *,
    location_id: str = "location-x",
    product_id: str = "product-a",
    channel: PreferredChannel = PreferredChannel.MOBILE,
    quantity: int = 2,
) -> PurchaseIntent:
    return PurchaseIntent(
        identifier,
        "basket-0-000001",
        "customer-a",
        location_id,
        product_id,
        channel,
        quantity,
        0,
    )


def promotion(
    identifier: str,
    rate: float,
    *,
    target_type: PromotionTargetType = PromotionTargetType.GLOBAL,
    target_ids: tuple[str, ...] = (),
    channel: PromotionChannel = PromotionChannel.ALL,
) -> ActivePromotion:
    return ActivePromotion(identifier, target_type, target_ids, channel, rate, 0.0)


def runtime(
    *,
    intents: tuple[PurchaseIntent, ...] = (intent(),),
    products: tuple[Product, ...] = (product(),),
    locations: tuple[Location, ...] = (location(),),
    inventory: tuple[InventoryItem, ...] = (
        InventoryItem("inventory-a", "location-x", "product-a", 0, 0, 10, True),
    ),
    promotions: tuple[ActivePromotion, ...] = (),
    seed: int = 42,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    store = EventStore()
    context = SimulationContext(
        seed,
        DateRange(NOW.date(), NOW.date()),
        RandomEngine(seed),
        EventBus(store),
    )
    clock = SimulationClock(TimeRange(NOW, NOW), TickUnit.HOUR)
    collections = {
        "products": products,
        "locations": locations,
        "inventory": inventory,
        "temporal_context": (TemporalContext(0, NOW, TickUnit.HOUR),),
        "promotion_context": (PromotionContext(0, NOW, promotions),),
        "customer_behavior_context": (
            CustomerBehaviorContext(
                0,
                NOW,
                intents,
                len(intents),
                sum(item.requested_quantity for item in intents),
                0,
            ),
        ),
    }
    for name, values in collections.items():
        collection = context.state.create_collection(name)
        for index, value in enumerate(values):
            key = (
                "tick-0"
                if name.endswith("_context")
                else getattr(value, "id", str(index))
            )
            collection.add(key, value)
    return context, clock, store


def execute(**kwargs: object) -> PricingContext:
    context, clock, _ = runtime(**kwargs)
    PricingEngine().execute(context, clock)
    result = context.state.collection("pricing_context").require("tick-0")
    assert isinstance(result, PricingContext)
    return result


def test_models_are_immutable_and_validate_money() -> None:
    quote = execute().quotes[0]
    assert isinstance(quote.unit_base_price, Decimal)
    with pytest.raises(FrozenInstanceError):
        quote.__setattr__("quantity", 3)
    with pytest.raises(ValueError, match="quantity"):
        PriceQuote(
            "i",
            "b",
            "c",
            "l",
            "p",
            PreferredChannel.MOBILE,
            0,
            "COP",
            Decimal("1.00"),
            ZERO_MONEY,
            Decimal("1.00"),
            ZERO_MONEY,
            ZERO_MONEY,
            ZERO_MONEY,
            (),
            0,
        )
    with pytest.raises(FrozenInstanceError):
        execute().__setattr__("currency", "USD")


def test_no_promotion_and_empty_context() -> None:
    quote = execute().quotes[0]
    assert quote.basket_id == "basket-0-000001"
    assert (
        quote.unit_base_price,
        quote.unit_discount_amount,
        quote.unit_effective_price,
        quote.gross_amount,
        quote.discount_amount,
        quote.net_amount,
    ) == (
        Decimal("100.00"),
        Decimal("0.00"),
        Decimal("100.00"),
        Decimal("200.00"),
        Decimal("0.00"),
        Decimal("200.00"),
    )
    empty = execute(intents=())
    assert empty.currency is None and empty.quotes == ()
    assert (
        empty.total_gross_amount,
        empty.total_discount_amount,
        empty.total_net_amount,
    ) == (
        ZERO_MONEY,
        ZERO_MONEY,
        ZERO_MONEY,
    )


def test_twenty_percent_discount_and_round_half_up() -> None:
    discounted = execute(
        intents=(intent(quantity=3),), promotions=(promotion("promo", 0.20),)
    ).quotes[0]
    assert discounted.unit_discount_amount == Decimal("20.00")
    assert discounted.unit_effective_price == Decimal("80.00")
    assert discounted.gross_amount == Decimal("300.00")
    assert discounted.discount_amount == Decimal("60.00")
    assert discounted.net_amount == Decimal("240.00")
    rounded = execute(
        products=(product(price=Decimal("9999.99")),),
        promotions=(promotion("promo", 0.15),),
    ).quotes[0]
    assert rounded.unit_discount_amount == Decimal("1500.00")
    assert rounded.unit_effective_price == Decimal("8499.99")


@pytest.mark.parametrize(
    "target_type,target_ids,discounted",
    [
        (PromotionTargetType.GLOBAL, (), True),
        (PromotionTargetType.REGION, ("region-a",), True),
        (PromotionTargetType.REGION, ("region-b",), False),
        (PromotionTargetType.LOCATION, ("location-x",), True),
        (PromotionTargetType.LOCATION, ("location-y",), False),
        (PromotionTargetType.CATEGORY, ("category-a",), True),
        (PromotionTargetType.CATEGORY, ("category-b",), False),
        (PromotionTargetType.PRODUCT, ("product-a",), True),
        (PromotionTargetType.PRODUCT, ("product-b",), False),
    ],
)
def test_promotion_targets(
    target_type: PromotionTargetType,
    target_ids: tuple[str, ...],
    discounted: bool,
) -> None:
    quote = execute(
        promotions=(
            promotion("promo", 0.20, target_type=target_type, target_ids=target_ids),
        )
    ).quotes[0]
    assert (quote.unit_discount_amount > 0) is discounted


@pytest.mark.parametrize(
    "promotion_channel,intent_channel,discounted",
    [
        (PromotionChannel.ALL, PreferredChannel.MOBILE, True),
        (PromotionChannel.ALL, PreferredChannel.PHYSICAL, True),
        (PromotionChannel.MOBILE, PreferredChannel.MOBILE, True),
        (PromotionChannel.MOBILE, PreferredChannel.PHYSICAL, False),
        (PromotionChannel.PHYSICAL, PreferredChannel.PHYSICAL, True),
        (PromotionChannel.PHYSICAL, PreferredChannel.MOBILE, False),
    ],
)
def test_promotion_channels(
    promotion_channel: PromotionChannel,
    intent_channel: PreferredChannel,
    discounted: bool,
) -> None:
    quote = execute(
        intents=(intent(channel=intent_channel),),
        promotions=(promotion("promo", 0.20, channel=promotion_channel),),
    ).quotes[0]
    assert (quote.unit_discount_amount > 0) is discounted


def test_location_promotion_does_not_leak() -> None:
    x, y = location("location-x"), location("location-y")
    quotes = execute(
        intents=(intent("intent-x"), intent("intent-y", location_id="location-y")),
        locations=(x, y),
        inventory=(
            InventoryItem("ix", x.id, "product-a", 0, 0, 10, True),
            InventoryItem("iy", y.id, "product-a", 0, 0, 10, True),
        ),
        promotions=(
            promotion(
                "promo-x",
                0.20,
                target_type=PromotionTargetType.LOCATION,
                target_ids=(x.id,),
            ),
        ),
    ).quotes
    assert quotes[0].applied_promotion_ids == ("promo-x",)
    assert quotes[1].applied_promotion_ids == ()


def test_highest_discount_wins_and_tie_preserves_order() -> None:
    quote = execute(
        promotions=(
            promotion("ten", 0.10),
            promotion("twenty", 0.20),
            promotion("fifteen", 0.15),
        )
    ).quotes[0]
    assert quote.applied_promotion_ids == ("twenty",)
    tied = execute(
        promotions=(promotion("first", 0.20), promotion("second", 0.20))
    ).quotes[0]
    assert tied.applied_promotion_ids == ("first",)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (
            {
                "inventory": (
                    InventoryItem("other", "location-y", "product-a", 0, 0, 1, True),
                )
            },
            "not offered",
        ),
        (
            {
                "inventory": (
                    InventoryItem(
                        "inactive", "location-x", "product-a", 0, 0, 1, False
                    ),
                )
            },
            "not offered",
        ),
        ({"locations": (location(opened=date(2026, 8, 16)),)}, "unopened"),
        ({"products": (product(active=False),)}, "inactive Product"),
    ],
)
def test_defensive_commercial_validation(
    kwargs: dict[str, object], message: str
) -> None:
    context, clock, store = runtime(**kwargs)
    with pytest.raises(ValueError, match=message):
        PricingEngine().execute(context, clock)
    assert not context.state.has_collection("pricing_context")
    assert store.count() == 0


def test_zero_or_insufficient_stock_still_quotes_full_quantity() -> None:
    for stock in (0, 2):
        quote = execute(
            intents=(intent(quantity=10),),
            inventory=(
                InventoryItem(
                    "inventory-a", "location-x", "product-a", stock, 0, 10, True
                ),
            ),
        ).quotes[0]
        assert quote.quantity == 10 and quote.gross_amount == Decimal("1000.00")


def test_multiple_currencies_fail() -> None:
    context, clock, _ = runtime(
        intents=(intent("i-a"), intent("i-b", product_id="product-b")),
        products=(product(), product("product-b", currency="USD")),
        inventory=(
            InventoryItem("ia", "location-x", "product-a", 0, 0, 1, True),
            InventoryItem("ib", "location-x", "product-b", 0, 0, 1, True),
        ),
    )
    with pytest.raises(ValueError, match="multiple currencies"):
        PricingEngine().execute(context, clock)


def test_invalid_applicable_discount_rate_fails() -> None:
    context, clock, _ = runtime(promotions=(promotion("invalid", 1.01),))
    with pytest.raises(ValueError, match="invalid discount_rate"):
        PricingEngine().execute(context, clock)


@pytest.mark.parametrize(
    "collection_name",
    ("temporal_context", "promotion_context", "customer_behavior_context"),
)
def test_current_tick_context_is_required(collection_name: str) -> None:
    context, clock, _ = runtime()
    context.state.collection(collection_name).remove("tick-0")
    with pytest.raises(ValueError, match=f"{collection_name} context is missing"):
        PricingEngine().execute(context, clock)


def test_event_save_before_publish_duplicate_and_seed_independence() -> None:
    first_context, first_clock, store = runtime(seed=1)
    observed: list[bool] = []
    first_context.event_bus.subscribe(
        "PricingContextGenerated",
        lambda event: observed.append(
            first_context.state.collection("pricing_context").contains("tick-0")
        ),
    )
    engine = PricingEngine()
    engine.execute(first_context, first_clock)
    first = first_context.state.collection("pricing_context").require("tick-0")
    second_context, second_clock, _ = runtime(seed=999)
    PricingEngine().execute(second_context, second_clock)
    assert first == second_context.state.collection("pricing_context").require("tick-0")
    assert observed == [True]
    event = store.all_events()[-1]
    assert event.payload["total_gross_amount"] == "200.00"
    assert event.payload["quotes"][0]["basket_id"] == "basket-0-000001"
    before = store.count()
    with pytest.raises(ValueError, match="already exists"):
        engine.execute(first_context, first_clock)
    assert store.count() == before
