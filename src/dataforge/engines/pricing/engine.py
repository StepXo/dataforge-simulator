"""Engine that prices validated purchase intents without creating sales."""

from decimal import ROUND_HALF_UP, Decimal

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.simulation_state import require_tick_context
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.pricing.events import PricingContextGenerated
from dataforge.engines.pricing.models import (
    ZERO_MONEY,
    PriceQuote,
    PricingContext,
)
from dataforge.engines.promotion.matching import promotion_matches_target
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.assortment import index_active_assortment
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionChannel

MONEY_QUANT = Decimal("0.01")
PRICING_CONTEXT_COLLECTION = "pricing_context"


class PricingEngine:
    """Create one deterministic monetary quote for every purchase intent."""

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        products = {
            product.id: product
            for product in self._typed_collection(context, "products", Product)
        }
        locations = {
            location.id: location
            for location in self._typed_collection(context, "locations", Location)
        }
        assortment = index_active_assortment(
            self._typed_collection(context, "inventory", InventoryItem)
        )
        temporal = require_tick_context(
            context.state,
            "temporal_context",
            clock.tick_index,
            TemporalContext,
            owner="pricing",
        )
        promotions = require_tick_context(
            context.state,
            "promotion_context",
            clock.tick_index,
            PromotionContext,
            owner="pricing",
        )
        behavior = require_tick_context(
            context.state,
            "customer_behavior_context",
            clock.tick_index,
            CustomerBehaviorContext,
            owner="pricing",
        )

        quotes = tuple(
            self._quote(intent, products, locations, assortment, temporal, promotions)
            for intent in behavior.intents
        )
        currencies = {quote.currency for quote in quotes}
        if len(currencies) > 1:
            raise ValueError("PricingContext cannot contain multiple currencies")
        currency = next(iter(currencies)) if currencies else None
        pricing = PricingContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            currency=currency,
            quotes=quotes,
            total_gross_amount=sum(
                (quote.gross_amount for quote in quotes), start=ZERO_MONEY
            ),
            total_discount_amount=sum(
                (quote.discount_amount for quote in quotes), start=ZERO_MONEY
            ),
            total_net_amount=sum(
                (quote.net_amount for quote in quotes), start=ZERO_MONEY
            ),
        )
        if context.state.has_collection(PRICING_CONTEXT_COLLECTION):
            collection = context.state.collection(PRICING_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(PRICING_CONTEXT_COLLECTION)
        collection.add(f"tick-{clock.tick_index}", pricing)
        context.event_bus.publish(PricingContextGenerated(pricing))

    def _quote(
        self,
        intent: PurchaseIntent,
        products: dict[str, Product],
        locations: dict[str, Location],
        assortment: dict[tuple[str, str], InventoryItem],
        temporal: TemporalContext,
        promotions: PromotionContext,
    ) -> PriceQuote:
        if intent.requested_quantity < 1:
            raise ValueError(f"PurchaseIntent has invalid quantity: {intent.id}")
        product = products.get(intent.product_id)
        if product is None:
            raise ValueError(f"PurchaseIntent references unknown Product: {intent.id}")
        if not product.active:
            raise ValueError(f"PurchaseIntent references inactive Product: {intent.id}")
        location = locations.get(intent.location_id)
        if location is None:
            raise ValueError(f"PurchaseIntent references unknown Location: {intent.id}")
        if location.opened_at > temporal.current_time.date():
            raise ValueError(
                f"PurchaseIntent references unopened Location: {intent.id}"
            )
        if (location.id, product.id) not in assortment:
            raise ValueError(
                "PurchaseIntent references Product not offered at Location: "
                f"{intent.id}"
            )

        selected = _best_promotion(intent, location, product, promotions)
        rate = Decimal("0")
        promotion_ids: tuple[str, ...] = ()
        if selected is not None:
            if not 0 <= selected.discount_rate <= 1:
                raise ValueError(
                    f"Promotion has invalid discount_rate: {selected.promotion_id}"
                )
            rate = Decimal(str(selected.discount_rate))
            promotion_ids = (selected.promotion_id,)

        unit_base = _quantize_money(product.base_price)
        unit_discount = _quantize_money(unit_base * rate)
        unit_effective = unit_base - unit_discount
        if unit_effective < 0:
            raise ValueError(f"Effective price cannot be negative: {intent.id}")
        quantity = Decimal(intent.requested_quantity)
        gross = _quantize_money(unit_base * quantity)
        discount = _quantize_money(unit_discount * quantity)
        net = _quantize_money(unit_effective * quantity)
        return PriceQuote(
            intent_id=intent.id,
            basket_id=intent.basket_id,
            customer_id=intent.customer_id,
            location_id=intent.location_id,
            product_id=intent.product_id,
            channel=intent.channel,
            quantity=intent.requested_quantity,
            currency=product.currency,
            unit_base_price=unit_base,
            unit_discount_amount=unit_discount,
            unit_effective_price=unit_effective,
            gross_amount=gross,
            discount_amount=discount,
            net_amount=net,
            applied_promotion_ids=promotion_ids,
            tick_index=temporal.tick_index,
        )

    def _typed_collection[T](
        self, context: SimulationContext, name: str, expected_type: type[T]
    ) -> tuple[T, ...]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required pricing collection is missing: {name}")
        values = context.state.collection(name).all()
        if not values:
            raise ValueError(f"Required pricing collection is empty: {name}")
        typed = tuple(value for value in values if isinstance(value, expected_type))
        if len(typed) != len(values):
            raise ValueError(f"Pricing dependency contains invalid records: {name}")
        return typed


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _best_promotion(
    intent: PurchaseIntent,
    location: Location,
    product: Product,
    context: PromotionContext,
) -> ActivePromotion | None:
    selected: ActivePromotion | None = None
    for promotion in context.active_promotions:
        if not _channel_applies(promotion, intent) or not promotion_matches_target(
            promotion, location, product
        ):
            continue
        if not 0 <= promotion.discount_rate <= 1:
            raise ValueError(
                f"Promotion has invalid discount_rate: {promotion.promotion_id}"
            )
        if selected is None or promotion.discount_rate > selected.discount_rate:
            selected = promotion
    return selected


def _channel_applies(promotion: ActivePromotion, intent: PurchaseIntent) -> bool:
    return promotion.channel is PromotionChannel.ALL or (
        promotion.channel.value == intent.channel.value
    )
