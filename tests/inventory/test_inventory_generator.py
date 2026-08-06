"""Tests for initial inventory bootstrap generation."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from dataforge.bootstrap.contracts import BootstrapGenerator
from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.configuration.geography import load_geography
from dataforge.configuration.products import load_product_catalog
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.customers.generator import CustomerGenerationConfig, CustomerGenerator
from dataforge.events.event import DomainEvent
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.generator import GeographyGenerator, LocationGenerationConfig
from dataforge.geography.models import Location
from dataforge.inventory.events import InventoryItemCreated
from dataforge.inventory.generator import (
    InventoryBootstrapGenerator,
    InventoryGenerationConfig,
    _calculate_initial_stock,
)
from dataforge.inventory.models import InventoryItem
from dataforge.products.generator import ProductGenerator
from dataforge.products.models import Product


def context(seed: int = 42) -> tuple[SimulationContext, EventStore]:
    store = EventStore()
    return SimulationContext(
        seed,
        DateRange(date(2026, 1, 1), date(2026, 12, 31)),
        RandomEngine(seed),
        EventBus(store),
    ), store


def bootstrap_dependencies(ctx: SimulationContext) -> None:
    GeographyGenerator(
        load_geography(Path("configs/geography/colombia.yaml")),
        LocationGenerationConfig(),
    ).generate(ctx)
    ProductGenerator(
        load_product_catalog(Path("configs/products/taqueria.yaml"))
    ).generate(ctx)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_initial_stock": -1},
        {"min_initial_stock": 2, "max_initial_stock": 1},
        {"min_reorder_point": -1},
        {"min_reorder_point": 2, "max_reorder_point": 1},
        {"max_stock_multiplier": 0.9},
        {"product_availability_probability": -0.1},
        {"product_availability_probability": 1.1},
    ],
)
def test_inventory_config_validation(kwargs: dict[str, int | float]) -> None:
    with pytest.raises(ValidationError):
        InventoryGenerationConfig(**kwargs)


def test_inventory_item_is_immutable() -> None:
    item = InventoryItem("inventory-a-b", "a", "b", 100, 20, 150, True)
    assert item.current_stock == 100 and item.location_id == "a"
    with pytest.raises(FrozenInstanceError):
        item.__setattr__("current_stock", 0)


def test_inventory_generator_invariants_events_and_inactive_product() -> None:
    ctx, store = context()
    locations = ctx.state.create_collection("locations")
    locations.add(
        "small",
        Location(
            "small",
            "Small",
            "city-a",
            "area-a",
            "region-a",
            "country-a",
            50,
            1.0,
            date(2020, 1, 1),
        ),
    )
    locations.add(
        "large",
        Location(
            "large",
            "Large",
            "city-b",
            "area-b",
            "region-b",
            "country-a",
            250,
            1.0,
            date(2020, 1, 1),
        ),
    )
    products = ctx.state.create_collection("products")
    for index, active in enumerate((True, True, True, False), 1):
        product = Product(
            f"p{index}",
            f"P{index}",
            "category",
            "COP",
            Decimal("100"),
            Decimal("50"),
            Decimal("0.5000"),
            0.5 + index * 0.2,
            active,
        )
        products.add(product.id, product)

    def stored(event: DomainEvent) -> None:
        identifier = event.payload["inventory_id"]
        assert isinstance(identifier, str)
        assert ctx.state.collection("inventory").contains(identifier)

    ctx.event_bus.subscribe("InventoryItemCreated", stored)
    InventoryBootstrapGenerator(InventoryGenerationConfig()).generate(ctx)

    items = [
        value
        for value in ctx.state.collection("inventory").all()
        if isinstance(value, InventoryItem)
    ]
    assert 2 <= len(items) <= 6
    assert {item.location_id for item in items} == {"small", "large"}
    assert len({(item.location_id, item.product_id) for item in items}) == len(items)
    assert len({item.id for item in items}) == len(items)
    assert all(50 <= item.current_stock <= 250 for item in items)
    assert all(
        item.reorder_point <= item.current_stock <= item.max_stock for item in items
    )
    assert all(item.active and item.product_id != "p4" for item in items)
    assert store.count() == len(items)
    assert all(isinstance(event, InventoryItemCreated) for event in store.all_events())


def test_capacity_and_activity_factor_influence_stock() -> None:
    config = InventoryGenerationConfig(min_initial_stock=50, max_initial_stock=250)
    baseline = _calculate_initial_stock(config, 0.5, 0.0, 0.5)
    high_capacity = _calculate_initial_stock(config, 0.5, 1.0, 0.5)
    high_activity = _calculate_initial_stock(config, 0.5, 0.0, 1.5)
    assert high_capacity > baseline
    assert high_activity > baseline


def test_zero_availability_still_creates_one_item_per_location() -> None:
    ctx, _ = context()
    bootstrap_dependencies(ctx)
    InventoryBootstrapGenerator(
        InventoryGenerationConfig(product_availability_probability=0)
    ).generate(ctx)
    location_count = ctx.state.collection("locations").count()
    assert ctx.state.collection("inventory").count() == location_count


def test_inventory_is_reproducible_and_duplicate_execution_fails() -> None:
    pairs = [context(seed) for seed in (42, 42, 43)]
    for ctx, _ in pairs:
        bootstrap_dependencies(ctx)
        InventoryBootstrapGenerator(InventoryGenerationConfig()).generate(ctx)
    snapshots = [ctx.state.collection("inventory").all() for ctx, _ in pairs]
    assert snapshots[0] == snapshots[1] and snapshots[0] != snapshots[2]
    with pytest.raises(ValueError, match="must be empty"):
        InventoryBootstrapGenerator(InventoryGenerationConfig()).generate(pairs[0][0])


def test_missing_dependencies_fail_in_explicit_bootstrap_order() -> None:
    ctx, _ = context()
    generator: BootstrapGenerator = InventoryBootstrapGenerator(
        InventoryGenerationConfig()
    )
    with pytest.raises(ValueError, match="missing: locations"):
        BootstrapRunner([generator]).run(ctx)
    ctx.state.create_collection("locations").add(
        "location",
        Location(
            "location",
            "Location",
            "city",
            "area",
            "region",
            "country",
            100,
            1.0,
            date(2020, 1, 1),
        ),
    )
    with pytest.raises(ValueError, match="missing: products"):
        BootstrapRunner([generator]).run(ctx)


def test_complete_bootstrap_runner() -> None:
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
            CustomerGenerator(CustomerGenerationConfig(count=25)),
            InventoryBootstrapGenerator(InventoryGenerationConfig()),
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
        "customers",
        "inventory",
    )
    assert summary.generators_executed == 4
    assert summary.collections_created == 9
