"""Bootstrap generator for reproducible initial inventory."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from dataforge.bootstrap.collections import prepare_empty_collections
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.collection import StateCollection
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.events import InventoryItemCreated
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product


class InventoryGenerationConfig(BaseModel):
    min_initial_stock: int = Field(default=50, ge=0)
    max_initial_stock: int = 250
    min_reorder_point: int = Field(default=10, ge=0)
    max_reorder_point: int = 40
    max_stock_multiplier: float = Field(default=1.50, ge=1.0)
    product_availability_probability: float = Field(default=0.90, ge=0, le=1)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.max_initial_stock < self.min_initial_stock:
            raise ValueError("max_initial_stock must be at least min_initial_stock")
        if self.max_reorder_point < self.min_reorder_point:
            raise ValueError("max_reorder_point must be at least min_reorder_point")
        return self


class InventoryBootstrapGenerator:
    def __init__(self, config: InventoryGenerationConfig) -> None:
        self._config = config

    def generate(self, context: SimulationContext) -> None:
        locations = self._require_locations(context)
        products = self._require_products(context)
        prepare_empty_collections(context.state, ("inventory",))
        inventory = context.state.collection("inventory")
        capacities = [location.capacity for location in locations]
        minimum_capacity = min(capacities)
        capacity_span = max(capacities) - minimum_capacity

        for location in locations:
            created = 0
            for product in products:
                if (
                    context.random_engine.uniform(0, 1)
                    > self._config.product_availability_probability
                ):
                    continue
                self._create_item(
                    context,
                    inventory,
                    location,
                    product,
                    minimum_capacity,
                    capacity_span,
                )
                created += 1
            if created == 0:
                product = context.random_engine.choice(products)
                self._create_item(
                    context,
                    inventory,
                    location,
                    product,
                    minimum_capacity,
                    capacity_span,
                )

    def _require_locations(self, context: SimulationContext) -> list[Location]:
        values = self._require_collection(context, "locations")
        locations = [value for value in values if isinstance(value, Location)]
        if len(locations) != len(values):
            raise ValueError("Location collection contains invalid records")
        return locations

    def _require_products(self, context: SimulationContext) -> list[Product]:
        values = self._require_collection(context, "products")
        products = [
            value for value in values if isinstance(value, Product) and value.active
        ]
        if not products:
            raise ValueError("Products collection has no active products")
        if any(not isinstance(value, Product) for value in values):
            raise ValueError("Products collection contains invalid records")
        return products

    def _require_collection(
        self, context: SimulationContext, name: str
    ) -> tuple[object, ...]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required inventory collection is missing: {name}")
        values = context.state.collection(name).all()
        if not values:
            raise ValueError(f"Required inventory collection is empty: {name}")
        return values

    def _create_item(
        self,
        context: SimulationContext,
        inventory: StateCollection[object],
        location: Location,
        product: Product,
        minimum_capacity: int,
        capacity_span: int,
    ) -> None:
        capacity_share = (
            0.5
            if capacity_span == 0
            else (location.capacity - minimum_capacity) / capacity_span
        )
        current_stock = _calculate_initial_stock(
            self._config,
            context.random_engine.uniform(0, 1),
            capacity_share,
            product.activity_factor,
        )
        reorder_point = min(
            current_stock,
            context.random_engine.randint(
                self._config.min_reorder_point,
                self._config.max_reorder_point,
            ),
        )
        max_stock = max(
            current_stock,
            reorder_point,
            round(
                current_stock
                * context.random_engine.uniform(1.0, self._config.max_stock_multiplier)
            ),
        )
        item = InventoryItem(
            id=f"inventory-{location.id}-{product.id}",
            location_id=location.id,
            product_id=product.id,
            current_stock=current_stock,
            reorder_point=reorder_point,
            max_stock=max_stock,
            active=True,
        )
        inventory.add(item.id, item)
        context.event_bus.publish(InventoryItemCreated(item))


def _calculate_initial_stock(
    config: InventoryGenerationConfig,
    random_share: float,
    capacity_share: float,
    activity_factor: float,
) -> int:
    activity_share = min(1.0, max(0.0, (activity_factor - 0.5) / 1.0))
    combined = 0.50 * random_share + 0.25 * capacity_share + 0.25 * activity_share
    span = config.max_initial_stock - config.min_initial_stock
    return min(
        config.max_initial_stock,
        max(
            config.min_initial_stock, config.min_initial_stock + round(span * combined)
        ),
    )
