"""Bootstrap generator for a reproducible promotion calendar."""

from datetime import date, timedelta
from typing import Self

from pydantic import BaseModel, Field, model_validator

from dataforge.bootstrap.collections import prepare_empty_collections
from dataforge.core.simulation_context import SimulationContext
from dataforge.generators.geography.models import Location, Region
from dataforge.generators.products.models import Category, Product
from dataforge.generators.promotions.events import PromotionCreated
from dataforge.generators.promotions.models import (
    Promotion,
    PromotionChannel,
    PromotionTargetType,
)


class PromotionGenerationConfig(BaseModel):
    count: int = Field(default=20, ge=1)
    min_duration_days: int = Field(default=2, ge=1)
    max_duration_days: int = 14
    min_discount_rate: float = Field(default=0.05, ge=0, le=1)
    max_discount_rate: float = Field(default=0.30, ge=0, le=1)
    min_demand_lift: float = Field(default=0.05, ge=0)
    max_demand_lift: float = 0.50
    mobile_only_probability: float = Field(default=0.20, ge=0, le=1)
    location_target_probability: float = Field(default=0.35, ge=0, le=1)
    region_target_probability: float = Field(default=0.20, ge=0, le=1)
    category_target_probability: float = Field(default=0.25, ge=0, le=1)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.max_duration_days < self.min_duration_days:
            raise ValueError("max_duration_days must be at least min_duration_days")
        if self.max_discount_rate < self.min_discount_rate:
            raise ValueError("max_discount_rate must be at least min_discount_rate")
        if self.max_demand_lift < self.min_demand_lift:
            raise ValueError("max_demand_lift must be at least min_demand_lift")
        return self


class PromotionBootstrapGenerator:
    def __init__(self, config: PromotionGenerationConfig) -> None:
        self._config = config

    def generate(self, context: SimulationContext) -> None:
        regions = self._typed_dependency(context, "regions", Region)
        locations = self._typed_dependency(context, "locations", Location)
        categories = self._typed_dependency(context, "categories", Category)
        all_products = self._typed_dependency(context, "products", Product)
        products = [product for product in all_products if product.active]
        if not products:
            raise ValueError("Products collection has no active products")
        prepare_empty_collections(context.state, ("promotions",))
        promotions = context.state.collection("promotions")

        for sequence in range(1, self._config.count + 1):
            start_date, end_date = self._dates(context)
            target_type, target_ids = self._target(
                context, regions, locations, categories, products
            )
            promotion = Promotion(
                id=f"promotion-{sequence:03d}",
                name=f"Promotion {sequence:03d}",
                start_date=start_date,
                end_date=end_date,
                target_type=target_type,
                target_ids=target_ids,
                channel=self._channel(context),
                discount_rate=round(
                    context.random_engine.uniform(
                        self._config.min_discount_rate,
                        self._config.max_discount_rate,
                    ),
                    4,
                ),
                demand_lift=round(
                    context.random_engine.uniform(
                        self._config.min_demand_lift,
                        self._config.max_demand_lift,
                    ),
                    4,
                ),
                active=True,
            )
            self._validate_target(promotion, regions, locations, categories, products)
            promotions.add(promotion.id, promotion)
            context.event_bus.publish(PromotionCreated(promotion))

    def _typed_dependency[T](
        self, context: SimulationContext, name: str, expected_type: type[T]
    ) -> list[T]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required promotion collection is missing: {name}")
        raw = context.state.collection(name).all()
        if not raw:
            raise ValueError(f"Required promotion collection is empty: {name}")
        values = [value for value in raw if isinstance(value, expected_type)]
        if len(values) != len(raw):
            raise ValueError(f"Promotion dependency contains invalid records: {name}")
        return values

    def _dates(self, context: SimulationContext) -> tuple[date, date]:
        """Create a horizon-independent annual pattern anchored in leap year 2000."""
        anchor = date(2000, 1, 1)
        start_date = anchor + timedelta(days=context.random_engine.randint(0, 365))
        duration = context.random_engine.randint(
            self._config.min_duration_days, self._config.max_duration_days
        )
        return start_date, start_date + timedelta(days=duration - 1)

    def _target(
        self,
        context: SimulationContext,
        regions: list[Region],
        locations: list[Location],
        categories: list[Category],
        products: list[Product],
    ) -> tuple[PromotionTargetType, tuple[str, ...]]:
        draw = context.random_engine.uniform(0, 1)
        location_limit = self._config.location_target_probability
        region_limit = location_limit + self._config.region_target_probability
        category_limit = region_limit + self._config.category_target_probability
        if draw < location_limit:
            return PromotionTargetType.LOCATION, (
                context.random_engine.choice(locations).id,
            )
        if draw < region_limit:
            return PromotionTargetType.REGION, (
                context.random_engine.choice(regions).id,
            )
        if draw < category_limit:
            return PromotionTargetType.CATEGORY, (
                context.random_engine.choice(categories).id,
            )
        if context.random_engine.uniform(0, 1) < 0.5:
            return PromotionTargetType.PRODUCT, (
                context.random_engine.choice(products).id,
            )
        return PromotionTargetType.GLOBAL, ()

    def _channel(self, context: SimulationContext) -> PromotionChannel:
        if context.random_engine.uniform(0, 1) < self._config.mobile_only_probability:
            return PromotionChannel.MOBILE
        if context.random_engine.uniform(0, 1) < 0.5:
            return PromotionChannel.ALL
        return PromotionChannel.PHYSICAL

    def _validate_target(
        self,
        promotion: Promotion,
        regions: list[Region],
        locations: list[Location],
        categories: list[Category],
        products: list[Product],
    ) -> None:
        valid_ids = {
            PromotionTargetType.REGION: {item.id for item in regions},
            PromotionTargetType.LOCATION: {item.id for item in locations},
            PromotionTargetType.CATEGORY: {item.id for item in categories},
            PromotionTargetType.PRODUCT: {item.id for item in products},
        }
        if promotion.target_type is PromotionTargetType.GLOBAL:
            if promotion.target_ids:
                raise ValueError("Global promotion must not have target IDs")
            return
        if len(promotion.target_ids) != 1:
            raise ValueError("Targeted promotion must have exactly one target ID")
        if promotion.target_ids[0] not in valid_ids[promotion.target_type]:
            raise ValueError(f"Invalid promotion target: {promotion.target_ids[0]}")
