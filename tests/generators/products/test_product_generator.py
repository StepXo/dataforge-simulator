"""Tests for product bootstrap generation."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from dataforge.bootstrap.contracts import BootstrapGenerator
from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.config.geography import load_geography
from dataforge.config.products import load_product_catalog
from dataforge.core.events.event import DomainEvent
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.generators.geography.generator import (
    GeographyGenerator,
    LocationGenerationConfig,
)
from dataforge.generators.products.generator import ProductGenerator
from dataforge.generators.products.models import Category, Product


def context(seed: int = 42) -> tuple[SimulationContext, EventStore]:
    store = EventStore()
    return SimulationContext(
        seed,
        DateRange(date(2026, 1, 1), date(2026, 12, 31)),
        RandomEngine(seed),
        EventBus(store),
    ), store


def test_product_generator_models_margin_and_events() -> None:
    catalog = load_product_catalog(Path("configs/products/taqueria.yaml"))
    ctx, store = context()
    fields = {
        "CategoryCreated": ("categories", "category_id"),
        "ProductCreated": ("products", "product_id"),
    }

    def stored(event: DomainEvent) -> None:
        collection, field = fields[event.event_type]
        identifier = event.payload[field]
        assert isinstance(identifier, str)
        assert ctx.state.collection(collection).contains(identifier)

    for event_type in fields:
        ctx.event_bus.subscribe(event_type, stored)
    ProductGenerator(catalog).generate(ctx)

    assert ctx.state.collection("categories").count() == 5
    assert ctx.state.collection("products").count() == 20
    category = ctx.state.collection("categories").all()[0]
    item = ctx.state.collection("products").require("taco-al-pastor")
    assert isinstance(category, Category) and isinstance(item, Product)
    assert item.base_price == Decimal("12000.00")
    assert item.base_cost == Decimal("5500.00")
    assert item.base_margin == Decimal("0.5417")
    assert item.activity_factor == 1.0
    assert item.currency == "COP" and item.active is True
    with pytest.raises(FrozenInstanceError):
        item.name = "changed"  # type: ignore[attr-defined]
    assert store.count() == 25
    assert all(
        isinstance(event.payload.get("base_price", ""), str)
        for event in store.all_events()
    )


def test_product_margin_exact_and_rounded() -> None:
    catalog = load_product_catalog(Path("configs/products/taqueria.yaml")).model_copy(
        update={
            "products": [
                load_product_catalog(Path("configs/products/taqueria.yaml"))
                .products[0]
                .model_copy(
                    update={"base_price": Decimal("100"), "base_cost": Decimal("60")}
                ),
                load_product_catalog(Path("configs/products/taqueria.yaml"))
                .products[1]
                .model_copy(
                    update={"base_price": Decimal("3"), "base_cost": Decimal("1")}
                ),
            ]
        }
    )
    ctx, _ = context()
    ProductGenerator(catalog).generate(ctx)
    products = [
        value
        for value in ctx.state.collection("products").all()
        if isinstance(value, Product)
    ]
    assert [product.base_margin for product in products] == [
        Decimal("0.4000"),
        Decimal("0.6667"),
    ]


def test_configured_product_activity_factor_is_preserved() -> None:
    catalog = load_product_catalog(Path("configs/products/taqueria.yaml"))
    configured = catalog.products[0].model_copy(update={"activity_factor": 3.0})
    ctx, _ = context()
    ProductGenerator(catalog.model_copy(update={"products": [configured]})).generate(
        ctx
    )
    product = ctx.state.collection("products").require(configured.id)
    assert isinstance(product, Product)
    assert product.activity_factor == 3.0


def test_reproducibility_duplicate_and_bootstrap_summary() -> None:
    catalog = load_product_catalog(Path("configs/products/taqueria.yaml"))
    contexts = [context(seed) for seed in (42, 42, 43)]
    for ctx, _ in contexts:
        ProductGenerator(catalog).generate(ctx)
    products = [ctx.state.collection("products").all() for ctx, _ in contexts]
    categories = [ctx.state.collection("categories").all() for ctx, _ in contexts]
    assert products[0] == products[1] == products[2]
    assert categories[0] == categories[1] == categories[2]
    with pytest.raises(ValueError, match="must be empty"):
        ProductGenerator(catalog).generate(contexts[0][0])
    runner_ctx, _ = context()
    generator: BootstrapGenerator = ProductGenerator(catalog)
    summary = BootstrapRunner([generator]).run(runner_ctx)
    assert (
        summary.generators_executed,
        summary.collections_created,
        summary.records_created,
    ) == (1, 2, 25)


def test_geography_and_product_generators_are_isolated() -> None:
    ctx, _ = context()
    summary = BootstrapRunner(
        [
            GeographyGenerator(
                load_geography(Path("configs/geography/colombia.yaml")),
                LocationGenerationConfig(),
            ),
            ProductGenerator(
                load_product_catalog(Path("configs/products/taqueria.yaml"))
            ),
        ]
    ).run(ctx)
    assert ctx.state.collection_names() == (
        "countries",
        "regions",
        "administrative_areas",
        "cities",
        "locations",
        "categories",
        "products",
    )
    assert summary.generators_executed == 2
    assert summary.collections_created == 7
