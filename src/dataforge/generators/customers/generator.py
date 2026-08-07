"""Bootstrap generator for a synthetic customer population."""

from datetime import date, timedelta
from typing import Self

from pydantic import BaseModel, Field, model_validator

from dataforge.bootstrap.collections import prepare_empty_collections
from dataforge.core.simulation_context import SimulationContext
from dataforge.generators.customers.events import CustomerCreated
from dataforge.generators.customers.models import (
    Customer,
    CustomerSegment,
    PreferredChannel,
)
from dataforge.generators.geography.models import City, Location, Region


class CustomerGenerationConfig(BaseModel):
    count: int = Field(default=1000, ge=1)
    min_purchase_frequency: float = Field(default=0.2, ge=0)
    max_purchase_frequency: float = 8.0
    mobile_preference_probability: float = Field(default=0.45, ge=0, le=1)
    inactive_probability: float = Field(default=0.10, ge=0, le=1)
    high_frequency_probability: float = Field(default=0.15, ge=0, le=1)

    @model_validator(mode="after")
    def validate_frequency_range(self) -> Self:
        if self.max_purchase_frequency < self.min_purchase_frequency:
            raise ValueError(
                "max_purchase_frequency must be at least min_purchase_frequency"
            )
        return self


class CustomerGenerator:
    def __init__(self, config: CustomerGenerationConfig) -> None:
        self._config = config

    def generate(self, context: SimulationContext) -> None:
        regions, cities, locations = self._require_geography(context)
        prepare_empty_collections(context.state, ("customers",))
        customers = context.state.collection("customers")

        region_ids = {region.id for region in regions}
        for sequence in range(1, self._config.count + 1):
            city = context.random_engine.choice(cities)
            if city.region_id not in region_ids:
                raise ValueError(f"City references unknown region: {city.id}")
            location = self._preferred_location(context, city, locations)
            segment = self._segment(context)
            customer = Customer(
                id=f"customer-{sequence:06d}",
                home_city_id=city.id,
                home_region_id=city.region_id,
                preferred_location_id=location.id,
                segment=segment,
                purchase_frequency=self._purchase_frequency(context, segment),
                preferred_channel=self._preferred_channel(context),
                promotion_sensitivity=round(context.random_engine.uniform(0, 1), 2),
                activity_factor=round(context.random_engine.uniform(0.50, 1.50), 2),
                registered_at=self._registered_at(context),
                active=segment is not CustomerSegment.INACTIVE,
            )
            customers.add(customer.id, customer)
            context.event_bus.publish(CustomerCreated(customer))

    def _require_geography(
        self, context: SimulationContext
    ) -> tuple[list[Region], list[City], list[Location]]:
        typed: list[list[object]] = []
        for name in ("regions", "cities", "locations"):
            if not context.state.has_collection(name):
                raise ValueError(f"Required geography collection is missing: {name}")
            values = list(context.state.collection(name).all())
            if not values:
                raise ValueError(f"Required geography collection is empty: {name}")
            typed.append(values)
        regions = [value for value in typed[0] if isinstance(value, Region)]
        cities = [value for value in typed[1] if isinstance(value, City)]
        locations = [value for value in typed[2] if isinstance(value, Location)]
        if (
            len(regions) != len(typed[0])
            or len(cities) != len(typed[1])
            or len(locations) != len(typed[2])
        ):
            raise ValueError("Geography collections contain invalid records")
        return regions, cities, locations

    def _preferred_location(
        self, context: SimulationContext, city: City, locations: list[Location]
    ) -> Location:
        candidates = [location for location in locations if location.city_id == city.id]
        if not candidates:
            candidates = [
                location
                for location in locations
                if location.region_id == city.region_id
            ]
        if not candidates:
            raise ValueError(f"No location available for city region: {city.region_id}")
        return context.random_engine.choice(candidates)

    def _segment(self, context: SimulationContext) -> CustomerSegment:
        if context.random_engine.uniform(0, 1) < self._config.inactive_probability:
            return CustomerSegment.INACTIVE
        if (
            context.random_engine.uniform(0, 1)
            < self._config.high_frequency_probability
        ):
            return CustomerSegment.FREQUENT
        if context.random_engine.uniform(0, 1) < 0.5:
            return CustomerSegment.OCCASIONAL
        return CustomerSegment.REGULAR

    def _purchase_frequency(
        self, context: SimulationContext, segment: CustomerSegment
    ) -> float:
        if segment is CustomerSegment.INACTIVE:
            return 0.0
        span = self._config.max_purchase_frequency - self._config.min_purchase_frequency
        bounds = {
            CustomerSegment.OCCASIONAL: (0.0, 0.2),
            CustomerSegment.REGULAR: (0.2, 0.5),
            CustomerSegment.FREQUENT: (0.5, 1.0),
        }
        lower_share, upper_share = bounds[segment]
        lower = self._config.min_purchase_frequency + span * lower_share
        upper = self._config.min_purchase_frequency + span * upper_share
        return round(context.random_engine.uniform(lower, upper), 2)

    def _preferred_channel(self, context: SimulationContext) -> PreferredChannel:
        if (
            context.random_engine.uniform(0, 1)
            < self._config.mobile_preference_probability
        ):
            return PreferredChannel.MOBILE
        return PreferredChannel.PHYSICAL

    def _registered_at(self, context: SimulationContext) -> date:
        start = context.date_range.start_date
        context.random_engine.uniform(0, 1)
        return start - timedelta(days=context.random_engine.randint(0, 3 * 365))
