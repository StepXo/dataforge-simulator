"""Engine that calculates potential aggregate demand for each tick."""

from math import floor
from typing import Self

from pydantic import BaseModel, Field, model_validator

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.simulation_state import require_tick_context
from dataforge.core.tick import TickUnit
from dataforge.engines.demand.events import DemandContextGenerated
from dataforge.engines.demand.models import DemandContext, DemandRecord
from dataforge.engines.promotion.matching import promotion_matches_target
from dataforge.engines.promotion.models import PromotionContext
from dataforge.engines.time.models import (
    TemporalContext,
    TimeOfDay,
    time_of_day_for_hour,
)
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionChannel

DEMAND_CONTEXT_COLLECTION = "demand_context"


class DemandEngineConfig(BaseModel):
    """Configure hourly baseline demand and per-tick safety limits."""

    base_demand_min: float = Field(default=0.10, ge=0)
    base_demand_max: float = 3.00
    weekend_factor: float = Field(default=1.20, ge=0)
    mid_month_factor: float = Field(default=1.10, ge=0)
    month_end_factor: float = Field(default=1.10, ge=0)
    early_morning_factor: float = Field(default=0.20, ge=0)
    morning_factor: float = Field(default=0.70, ge=0)
    lunch_factor: float = Field(default=1.40, ge=0)
    afternoon_factor: float = Field(default=0.90, ge=0)
    evening_factor: float = Field(default=1.50, ge=0)
    night_factor: float = Field(default=0.60, ge=0)
    max_requested_units_per_item: int = Field(default=1000, ge=1)

    @model_validator(mode="after")
    def validate_base_demand_range(self) -> Self:
        if self.base_demand_max < self.base_demand_min:
            raise ValueError("base_demand_max must be at least base_demand_min")
        return self


class DemandEngine:
    """Generate potential demand for each active inventory assortment item."""

    def __init__(self, config: DemandEngineConfig | None = None) -> None:
        self._config = config or DemandEngineConfig()

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        """Generate demand without mutating products, stock, or the clock."""
        locations = {
            location.id: location
            for location in self._typed_collection(context, "locations", Location)
        }
        products = {
            product.id: product
            for product in self._typed_collection(context, "products", Product)
        }
        inventory = self._typed_collection(context, "inventory", InventoryItem)
        temporal = require_tick_context(
            context.state,
            "temporal_context",
            clock.tick_index,
            TemporalContext,
            owner="demand",
        )
        promotion = require_tick_context(
            context.state,
            "promotion_context",
            clock.tick_index,
            PromotionContext,
            owner="demand",
        )
        temporal_factor = _temporal_factor(temporal, self._config)
        demands: list[DemandRecord] = []

        for item in inventory:
            if not item.active:
                continue
            location = locations.get(item.location_id)
            product = products.get(item.product_id)
            if location is None:
                raise ValueError(f"Inventory references unknown location: {item.id}")
            if product is None:
                raise ValueError(f"Inventory references unknown product: {item.id}")
            if location.opened_at > temporal.current_time.date():
                continue
            if not product.active:
                continue
            base_demand = context.random_engine.uniform(
                self._config.base_demand_min,
                self._config.base_demand_max,
            )
            expected = _expected_demand(
                base_demand,
                location.activity_factor,
                product.activity_factor,
                temporal_factor,
                _promotion_factor(promotion, location, product),
            )
            requested = min(
                _stochastic_round(expected, context.random_engine),
                self._config.max_requested_units_per_item,
            )
            demands.append(
                DemandRecord(
                    location_id=location.id,
                    product_id=product.id,
                    expected_demand=expected,
                    requested_units=requested,
                )
            )

        demand_context = DemandContext(
            tick_index=clock.tick_index,
            current_time=temporal.current_time,
            demands=tuple(demands),
            total_requested_units=sum(record.requested_units for record in demands),
        )
        if context.state.has_collection(DEMAND_CONTEXT_COLLECTION):
            collection = context.state.collection(DEMAND_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(DEMAND_CONTEXT_COLLECTION)
        collection.add(f"tick-{clock.tick_index}", demand_context)
        context.event_bus.publish(DemandContextGenerated(demand_context))

    def _typed_collection[T](
        self,
        context: SimulationContext,
        name: str,
        expected_type: type[T],
    ) -> tuple[T, ...]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required demand collection is missing: {name}")
        values = context.state.collection(name).all()
        if not values:
            raise ValueError(f"Required demand collection is empty: {name}")
        typed = tuple(value for value in values if isinstance(value, expected_type))
        if len(typed) != len(values):
            raise ValueError(f"Demand dependency contains invalid records: {name}")
        return typed


def _expected_demand(
    base_demand: float,
    location_factor: float,
    product_factor: float,
    temporal_factor: float,
    promotion_factor: float,
) -> float:
    return round(
        max(
            0.0,
            base_demand
            * location_factor
            * product_factor
            * temporal_factor
            * promotion_factor,
        ),
        4,
    )


def _temporal_factor(
    temporal: TemporalContext,
    config: DemandEngineConfig,
) -> float:
    result = _intraday_factor(temporal.tick_unit, temporal.hour, config)
    if temporal.is_weekend:
        result *= config.weekend_factor
    if temporal.is_mid_month:
        result *= config.mid_month_factor
    if temporal.is_month_end:
        result *= config.month_end_factor
    return result


def _time_of_day_factor(
    time_of_day: TimeOfDay,
    config: DemandEngineConfig,
) -> float:
    factors = {
        TimeOfDay.EARLY_MORNING: config.early_morning_factor,
        TimeOfDay.MORNING: config.morning_factor,
        TimeOfDay.LUNCH: config.lunch_factor,
        TimeOfDay.AFTERNOON: config.afternoon_factor,
        TimeOfDay.EVENING: config.evening_factor,
        TimeOfDay.NIGHT: config.night_factor,
    }
    return factors[time_of_day]


def _intraday_factor(
    tick_unit: TickUnit,
    hour: int,
    config: DemandEngineConfig,
) -> float:
    """Scale the hourly baseline to the duration represented by one tick."""
    if tick_unit is TickUnit.HOUR:
        return _time_of_day_factor(time_of_day_for_hour(hour), config)
    if tick_unit is TickUnit.DAY:
        return sum(
            _time_of_day_factor(time_of_day_for_hour(day_hour), config)
            for day_hour in range(24)
        )
    raise ValueError(f"Unsupported tick unit for demand: {tick_unit}")


def _promotion_factor(
    promotion_context: PromotionContext,
    location: Location,
    product: Product,
) -> float:
    factor = 1.0
    for promotion in promotion_context.active_promotions:
        if promotion.channel is PromotionChannel.ALL and promotion_matches_target(
            promotion, location, product
        ):
            factor *= 1 + promotion.demand_lift
    return factor


def _stochastic_round(expected_demand: float, random_engine: RandomEngine) -> int:
    base = floor(expected_demand)
    fraction = expected_demand - base
    if fraction == 0:
        return base
    return base + int(random_engine.uniform(0, 1) < fraction)
