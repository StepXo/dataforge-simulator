"""Engine that assigns aggregate demand to concrete customers."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.customers.models import Customer, CustomerSegment, PreferredChannel
from dataforge.engines.customer_behavior.events import CustomerBehaviorContextGenerated
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.geography.models import Location
from dataforge.inventory.models import InventoryItem
from dataforge.products.models import Product
from dataforge.promotions.models import PromotionChannel, PromotionTargetType

CUSTOMER_BEHAVIOR_CONTEXT_COLLECTION = "customer_behavior_context"


class CustomerBehaviorEngineConfig(BaseModel):
    max_units_per_intent: int = Field(default=4, ge=1)
    occasional_activity_factor: float = Field(default=0.60, ge=0)
    regular_activity_factor: float = Field(default=1.00, ge=0)
    frequent_activity_factor: float = Field(default=1.40, ge=0)
    preferred_location_bonus: float = Field(default=1.50, ge=0)
    preferred_channel_bonus: float = Field(default=1.30, ge=0)
    promotion_sensitivity_weight: float = Field(default=0.50, ge=0)


@dataclass(slots=True)
class _IntentDraft:
    customer_id: str
    location_id: str
    product_id: str
    channel: PreferredChannel
    requested_quantity: int


class CustomerBehaviorEngine:
    """Convert aggregate demand into reproducible customer purchase intents."""

    def __init__(self, config: CustomerBehaviorEngineConfig | None = None) -> None:
        self._config = config or CustomerBehaviorEngineConfig()

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        customers = self._typed_collection(context, "customers", Customer)
        locations = {
            location.id: location
            for location in self._typed_collection(context, "locations", Location)
        }
        products = {
            product.id: product
            for product in self._typed_collection(context, "products", Product)
        }
        inventory = self._typed_collection(context, "inventory", InventoryItem)
        assortment: dict[tuple[str, str], InventoryItem] = {}
        for item in inventory:
            if not item.active:
                continue
            key = (item.location_id, item.product_id)
            if key in assortment:
                raise ValueError(
                    "Multiple active InventoryItems exist for commercial combination: "
                    f"{item.location_id}/{item.product_id}"
                )
            assortment[key] = item
        temporal = self._tick_context(
            context, "temporal_context", clock.tick_index, TemporalContext
        )
        promotions = self._tick_context(
            context, "promotion_context", clock.tick_index, PromotionContext
        )
        demand = self._tick_context(
            context, "demand_context", clock.tick_index, DemandContext
        )

        drafts: list[_IntentDraft] = []
        unassigned = 0
        for record in demand.demands:
            location = locations.get(record.location_id)
            product = products.get(record.product_id)
            if location is None or product is None:
                raise ValueError(
                    "Demand references unknown location or product: "
                    f"{record.location_id}/{record.product_id}"
                )
            if (
                location.id,
                product.id,
            ) not in assortment or location.opened_at > temporal.current_time.date():
                unassigned += record.requested_units
                continue
            eligible = tuple(
                customer
                for customer in customers
                if _is_eligible(customer, location, temporal)
            )
            assigned = self._assign_record(
                record,
                eligible,
                location,
                product,
                promotions,
                context.random_engine,
                drafts,
            )
            unassigned += record.requested_units - assigned

        intents = tuple(
            PurchaseIntent(
                id=f"intent-{clock.tick_index}-{index:06d}",
                customer_id=draft.customer_id,
                location_id=draft.location_id,
                product_id=draft.product_id,
                channel=draft.channel,
                requested_quantity=draft.requested_quantity,
                demand_tick_index=demand.tick_index,
            )
            for index, draft in enumerate(drafts, start=1)
        )
        behavior = CustomerBehaviorContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            intents=intents,
            total_intents=len(intents),
            total_requested_units=sum(intent.requested_quantity for intent in intents),
            unassigned_demand_units=unassigned,
        )
        if context.state.has_collection(CUSTOMER_BEHAVIOR_CONTEXT_COLLECTION):
            collection = context.state.collection(CUSTOMER_BEHAVIOR_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(
                CUSTOMER_BEHAVIOR_CONTEXT_COLLECTION
            )
        collection.add(f"tick-{clock.tick_index}", behavior)
        context.event_bus.publish(CustomerBehaviorContextGenerated(behavior))

    def _assign_record(
        self,
        record: DemandRecord,
        customers: tuple[Customer, ...],
        location: Location,
        product: Product,
        promotions: PromotionContext,
        random_engine: RandomEngine,
        drafts: list[_IntentDraft],
    ) -> int:
        weights = tuple(
            _customer_weight(customer, location, product, promotions, self._config)
            for customer in customers
        )
        if not customers or sum(weights) <= 0:
            return 0

        assigned = 0
        while assigned < record.requested_units:
            customer = random_engine.weighted_choice(customers, weights)
            channel = _select_channel(
                customer,
                location,
                product,
                promotions,
                self._config,
                random_engine,
            )
            quantity = random_engine.randint(
                1,
                min(
                    self._config.max_units_per_intent,
                    record.requested_units - assigned,
                ),
            )
            _append_or_consolidate(
                drafts,
                customer,
                location,
                product,
                channel,
                quantity,
                self._config.max_units_per_intent,
            )
            assigned += quantity
        return assigned

    def _typed_collection[T](
        self, context: SimulationContext, name: str, expected_type: type[T]
    ) -> tuple[T, ...]:
        if not context.state.has_collection(name):
            raise ValueError(
                f"Required customer behavior collection is missing: {name}"
            )
        values = context.state.collection(name).all()
        if not values:
            raise ValueError(f"Required customer behavior collection is empty: {name}")
        typed = tuple(value for value in values if isinstance(value, expected_type))
        if len(typed) != len(values):
            raise ValueError(
                f"Customer behavior dependency has invalid records: {name}"
            )
        return typed

    def _tick_context[T](
        self,
        context: SimulationContext,
        name: str,
        tick_index: int,
        expected_type: type[T],
    ) -> T:
        if not context.state.has_collection(name):
            raise ValueError(
                f"Required customer behavior collection is missing: {name}"
            )
        value = context.state.collection(name).get(f"tick-{tick_index}")
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for tick: {tick_index}")
        return value


def _is_eligible(
    customer: Customer, location: Location, temporal: TemporalContext
) -> bool:
    return (
        customer.active
        and customer.segment is not CustomerSegment.INACTIVE
        and customer.registered_at <= temporal.current_time.date()
        and location.opened_at <= temporal.current_time.date()
        and customer.home_city_id == location.city_id
        and customer.home_region_id == location.region_id
    )


def _customer_weight(
    customer: Customer,
    location: Location,
    product: Product,
    promotions: PromotionContext,
    config: CustomerBehaviorEngineConfig,
) -> float:
    segment_factors = {
        CustomerSegment.OCCASIONAL: config.occasional_activity_factor,
        CustomerSegment.REGULAR: config.regular_activity_factor,
        CustomerSegment.FREQUENT: config.frequent_activity_factor,
        CustomerSegment.INACTIVE: 0.0,
    }
    location_factor = (
        config.preferred_location_bonus
        if customer.preferred_location_id == location.id
        else 1.0
    )
    promotion_factor = _promotion_propensity(
        customer,
        location,
        product,
        promotions,
        PromotionChannel.ALL,
        config,
    )
    return (
        segment_factors[customer.segment]
        * customer.purchase_frequency
        * customer.activity_factor
        * location_factor
        * promotion_factor
    )


def _select_channel(
    customer: Customer,
    location: Location,
    product: Product,
    promotions: PromotionContext,
    config: CustomerBehaviorEngineConfig,
    random_engine: RandomEngine,
) -> PreferredChannel:
    channels = (PreferredChannel.PHYSICAL, PreferredChannel.MOBILE)
    weights = tuple(
        (
            config.preferred_channel_bonus
            if channel is customer.preferred_channel
            else 1.0
        )
        * _promotion_propensity(
            customer,
            location,
            product,
            promotions,
            PromotionChannel(channel.value),
            config,
        )
        for channel in channels
    )
    return random_engine.weighted_choice(channels, weights)


def _promotion_propensity(
    customer: Customer,
    location: Location,
    product: Product,
    promotions: PromotionContext,
    channel: PromotionChannel,
    config: CustomerBehaviorEngineConfig,
) -> float:
    factor = 1.0
    for promotion in promotions.active_promotions:
        if promotion.channel not in (PromotionChannel.ALL, channel):
            continue
        if _promotion_applies(promotion, location, product):
            factor *= 1 + (
                customer.promotion_sensitivity * config.promotion_sensitivity_weight
            )
    return factor


def _promotion_applies(
    promotion: ActivePromotion, location: Location, product: Product
) -> bool:
    if promotion.target_type is PromotionTargetType.GLOBAL:
        return True
    target = {
        PromotionTargetType.REGION: location.region_id,
        PromotionTargetType.LOCATION: location.id,
        PromotionTargetType.CATEGORY: product.category_id,
        PromotionTargetType.PRODUCT: product.id,
    }[promotion.target_type]
    return target in promotion.target_ids


def _append_or_consolidate(
    drafts: list[_IntentDraft],
    customer: Customer,
    location: Location,
    product: Product,
    channel: PreferredChannel,
    quantity: int,
    maximum: int,
) -> None:
    for draft in drafts:
        if (
            draft.customer_id == customer.id
            and draft.location_id == location.id
            and draft.product_id == product.id
            and draft.channel is channel
            and draft.requested_quantity < maximum
        ):
            available = maximum - draft.requested_quantity
            moved = min(available, quantity)
            draft.requested_quantity += moved
            quantity -= moved
            if quantity == 0:
                return
    while quantity > 0:
        moved = min(maximum, quantity)
        drafts.append(
            _IntentDraft(
                customer.id,
                location.id,
                product.id,
                channel,
                moved,
            )
        )
        quantity -= moved
