"""Engine that assigns aggregate demand to concrete customers."""

from dataclasses import dataclass
from datetime import timedelta
from math import exp

from pydantic import BaseModel, Field

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import TICK_DELTAS, SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.simulation_state import require_tick_context
from dataforge.core.value_objects import build_tick_sequence_id
from dataforge.engines.customer_behavior.events import CustomerBehaviorContextGenerated
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.matching import promotion_matches_target
from dataforge.engines.promotion.models import PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.generators.customers.models import Customer, PreferredChannel
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.assortment import index_active_assortment
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionChannel

CUSTOMER_BEHAVIOR_CONTEXT_COLLECTION = "customer_behavior_context"


class CustomerBehaviorEngineConfig(BaseModel):
    max_units_per_intent: int = Field(default=4, ge=1)
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


def _build_intents(
    drafts: list[_IntentDraft], tick_index: int, demand_tick_index: int
) -> tuple[PurchaseIntent, ...]:
    basket_ids: dict[tuple[str, str, PreferredChannel], str] = {}
    intents: list[PurchaseIntent] = []
    for index, draft in enumerate(drafts, start=1):
        basket_key = (draft.customer_id, draft.location_id, draft.channel)
        if basket_key not in basket_ids:
            basket_ids[basket_key] = build_tick_sequence_id(
                "basket", tick_index, len(basket_ids) + 1
            )
        intents.append(
            PurchaseIntent(
                id=build_tick_sequence_id("intent", tick_index, index),
                basket_id=basket_ids[basket_key],
                customer_id=draft.customer_id,
                location_id=draft.location_id,
                product_id=draft.product_id,
                channel=draft.channel,
                requested_quantity=draft.requested_quantity,
                demand_tick_index=demand_tick_index,
            )
        )
    return tuple(intents)


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
        assortment = index_active_assortment(inventory)
        temporal = require_tick_context(
            context.state,
            "temporal_context",
            clock.tick_index,
            TemporalContext,
            owner="customer behavior",
        )
        promotions = require_tick_context(
            context.state,
            "promotion_context",
            clock.tick_index,
            PromotionContext,
            owner="customer behavior",
        )
        demand = require_tick_context(
            context.state,
            "demand_context",
            clock.tick_index,
            DemandContext,
            owner="customer behavior",
        )

        drafts: list[_IntentDraft] = []
        unassigned = 0
        available_customer_ids = {
            customer.id
            for customer in customers
            if _is_temporally_available(customer, clock, context.random_engine)
        }
        basket_assignments: dict[str, tuple[str, PreferredChannel]] = {}
        assigned_products: set[tuple[str, str]] = set()
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
                if customer.id in available_customer_ids
                and (
                    customer.id not in basket_assignments
                    or basket_assignments[customer.id][0] == location.id
                )
                and _is_eligible(customer, location, temporal)
            )
            assigned = self._assign_record(
                record,
                eligible,
                location,
                product,
                promotions,
                context.random_engine,
                drafts,
                basket_assignments,
                assigned_products,
            )
            unassigned += record.requested_units - assigned

        intent_values = _build_intents(drafts, clock.tick_index, demand.tick_index)
        behavior = CustomerBehaviorContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            intents=intent_values,
            total_intents=len(intent_values),
            total_requested_units=sum(
                intent.requested_quantity for intent in intent_values
            ),
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
        basket_assignments: dict[str, tuple[str, PreferredChannel]],
        assigned_products: set[tuple[str, str]],
    ) -> int:
        if not customers:
            return 0

        assigned = 0
        while assigned < record.requested_units:
            unused = [
                customer
                for customer in customers
                if customer.id not in basket_assignments
                and (customer.id, product.id) not in assigned_products
            ]
            candidates = unused or [
                customer
                for customer in customers
                if basket_assignments[customer.id][0] == location.id
                and (customer.id, product.id) not in assigned_products
            ]
            if not candidates:
                break
            weights = tuple(
                _customer_weight(customer, location, product, promotions, self._config)
                for customer in candidates
            )
            if sum(weights) <= 0:
                break
            customer = random_engine.weighted_choice(candidates, weights)
            assignment = basket_assignments.get(customer.id)
            if assignment is None:
                channel = _select_channel(
                    customer,
                    location,
                    product,
                    promotions,
                    self._config,
                    random_engine,
                )
                basket_assignments[customer.id] = (location.id, channel)
            else:
                channel = assignment[1]
            assigned_products.add((customer.id, product.id))
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


def _is_eligible(
    customer: Customer, location: Location, temporal: TemporalContext
) -> bool:
    return (
        customer.active
        and customer.purchase_frequency > 0
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
    return customer.activity_factor * location_factor * promotion_factor


_AVERAGE_MONTH = timedelta(days=365.25 / 12)


def activity_probability(monthly_rate: float, clock: SimulationClock) -> float:
    """Convert an expected monthly rate into availability for one tick."""
    if monthly_rate <= 0:
        return 0.0
    month_fraction = (
        TICK_DELTAS[clock.tick_unit].total_seconds() / _AVERAGE_MONTH.total_seconds()
    )
    return 1 - exp(-(monthly_rate * month_fraction))


def _is_temporally_available(
    customer: Customer,
    clock: SimulationClock,
    random_engine: RandomEngine,
) -> bool:
    if not customer.active or customer.purchase_frequency <= 0:
        return False
    return random_engine.uniform(0, 1) < activity_probability(
        customer.purchase_frequency, clock
    )


def _select_channel(
    customer: Customer,
    location: Location,
    product: Product,
    promotions: PromotionContext,
    config: CustomerBehaviorEngineConfig,
    random_engine: RandomEngine,
) -> PreferredChannel:
    # Channel distribution is configured when customer preferences are generated.
    # The runtime must not dilute that configured distribution with a second draw.
    return customer.preferred_channel


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
        if promotion_matches_target(promotion, location, product):
            factor *= 1 + (
                customer.promotion_sensitivity * config.promotion_sensitivity_weight
            )
    return factor


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
