"""Events published while bootstrapping products."""

from dataforge.events.event import DomainEvent
from dataforge.products.models import Category, Product


class CategoryCreated(DomainEvent):
    def __init__(self, category: Category) -> None:
        super().__init__(
            event_type="CategoryCreated",
            payload={"category_id": category.id, "name": category.name},
        )


class ProductCreated(DomainEvent):
    def __init__(self, product: Product) -> None:
        super().__init__(
            event_type="ProductCreated",
            payload={
                "product_id": product.id,
                "name": product.name,
                "category_id": product.category_id,
                "currency": product.currency,
                "base_price": format(product.base_price, "f"),
                "base_cost": format(product.base_cost, "f"),
                "base_margin": format(product.base_margin, "f"),
                "activity_factor": product.activity_factor,
                "active": product.active,
            },
        )
