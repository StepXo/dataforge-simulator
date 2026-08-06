"""Bootstrap generator for configured products."""

from decimal import ROUND_HALF_UP, Decimal

from dataforge.configuration.products.models import ProductCatalogDefinition
from dataforge.core.simulation_context import SimulationContext
from dataforge.products.events import CategoryCreated, ProductCreated
from dataforge.products.models import Category, Product

COLLECTION_NAMES = ("categories", "products")
MARGIN_QUANTUM = Decimal("0.0001")


class ProductGenerator:
    def __init__(self, catalog: ProductCatalogDefinition) -> None:
        self._catalog = catalog

    def generate(self, context: SimulationContext) -> None:
        self._prepare_collections(context)
        category_ids: set[str] = set()
        categories = context.state.collection("categories")
        for category_definition in self._catalog.categories:
            category = Category(category_definition.id, category_definition.name)
            categories.add(category.id, category)
            context.event_bus.publish(CategoryCreated(category))
            category_ids.add(category.id)

        products = context.state.collection("products")
        for product_definition in self._catalog.products:
            if product_definition.category_id not in category_ids:
                raise ValueError(
                    f"Unknown product category: {product_definition.category_id}"
                )
            margin = (
                (product_definition.base_price - product_definition.base_cost)
                / product_definition.base_price
            ).quantize(MARGIN_QUANTUM, rounding=ROUND_HALF_UP)
            product = Product(
                id=product_definition.id,
                name=product_definition.name,
                category_id=product_definition.category_id,
                currency=self._catalog.currency,
                base_price=product_definition.base_price,
                base_cost=product_definition.base_cost,
                base_margin=margin,
                activity_factor=round(context.random_engine.uniform(0.50, 1.50), 2),
                active=product_definition.active,
            )
            products.add(product.id, product)
            context.event_bus.publish(ProductCreated(product))

    def _prepare_collections(self, context: SimulationContext) -> None:
        for name in COLLECTION_NAMES:
            if (
                context.state.has_collection(name)
                and context.state.collection(name).count() > 0
            ):
                raise ValueError(f"State collection must be empty: {name}")
        for name in COLLECTION_NAMES:
            if not context.state.has_collection(name):
                context.state.create_collection(name)
