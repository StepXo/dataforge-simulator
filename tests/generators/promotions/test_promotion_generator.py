"""Tests for promotion calendar bootstrap generation."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from dataforge.generators.customers.generator import (
    CustomerGenerationConfig,
    CustomerGenerator,
)
from dataforge.generators.geography.generator import (
    GeographyGenerator,
    LocationGenerationConfig,
)
from dataforge.generators.inventory.generator import (
    InventoryBootstrapGenerator,
    InventoryGenerationConfig,
)
from dataforge.generators.products.generator import ProductGenerator
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.events import PromotionCreated
from dataforge.generators.promotions.generator import (
    PromotionBootstrapGenerator,
    PromotionGenerationConfig,
)
from dataforge.generators.promotions.models import (
    Promotion,
    PromotionChannel,
    PromotionTargetType,
)


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
        {"count": 0},
        {"min_duration_days": 0},
        {"min_duration_days": 3, "max_duration_days": 2},
        {"min_discount_rate": -0.1},
        {"max_discount_rate": 1.1},
        {"min_discount_rate": 0.5, "max_discount_rate": 0.4},
        {"min_demand_lift": -0.1},
        {"min_demand_lift": 1, "max_demand_lift": 0.5},
        {"mobile_only_probability": -0.1},
        {"location_target_probability": 1.1},
        {"region_target_probability": -0.1},
        {"category_target_probability": 1.1},
    ],
)
def test_promotion_config_validation(kwargs: dict[str, int | float]) -> None:
    with pytest.raises(ValidationError):
        PromotionGenerationConfig(**kwargs)


def test_promotion_is_immutable() -> None:
    promotion = Promotion(
        "promotion-001",
        "Promotion 001",
        date(2026, 1, 1),
        date(2026, 1, 2),
        PromotionTargetType.GLOBAL,
        (),
        PromotionChannel.ALL,
        0.1,
        0.2,
        True,
    )
    assert promotion.target_ids == () and promotion.channel is PromotionChannel.ALL
    with pytest.raises(FrozenInstanceError):
        promotion.__setattr__("active", False)


def test_promotion_generator_invariants_targets_events_and_inactive_product() -> None:
    ctx, store = context()
    bootstrap_dependencies(ctx)
    inactive = Product(
        "inactive",
        "Inactive",
        "tacos",
        "COP",
        Decimal("100"),
        Decimal("50"),
        Decimal("0.5000"),
        1.0,
        False,
    )
    ctx.state.collection("products").add(inactive.id, inactive)
    dependencies = {
        "region": {item.id for item in ctx.state.collection("regions").all()},
        "location": {item.id for item in ctx.state.collection("locations").all()},
        "category": {item.id for item in ctx.state.collection("categories").all()},
        "product": {
            item.id
            for item in ctx.state.collection("products").all()
            if isinstance(item, Product) and item.active
        },
    }

    def stored(event: DomainEvent) -> None:
        identifier = event.payload["promotion_id"]
        assert isinstance(identifier, str)
        assert ctx.state.collection("promotions").contains(identifier)

    ctx.event_bus.subscribe("PromotionCreated", stored)
    PromotionBootstrapGenerator(PromotionGenerationConfig(count=100)).generate(ctx)
    promotions = [
        item
        for item in ctx.state.collection("promotions").all()
        if isinstance(item, Promotion)
    ]
    assert len(promotions) == 100
    assert [item.id for item in promotions] == [
        f"promotion-{index:03d}" for index in range(1, 101)
    ]
    for item in promotions:
        assert (
            date(2000, 1, 1) <= item.start_date <= date(2000, 12, 31)
            and item.end_date >= item.start_date
        )
        assert 1 <= (item.end_date - item.start_date).days + 1 <= 14
        assert 0.05 <= item.discount_rate <= 0.30
        assert 0.05 <= item.demand_lift <= 0.50
        assert item.channel in PromotionChannel and item.active is True
        if item.target_type is PromotionTargetType.GLOBAL:
            assert item.target_ids == ()
        else:
            assert len(item.target_ids) == 1
            assert item.target_ids[0] in dependencies[item.target_type.value]
            assert item.target_ids[0] != "inactive"
    assert {item.target_type for item in promotions} == set(PromotionTargetType)
    assert len({item.start_date for item in promotions}) > 1
    promotion_events = [
        event for event in store.all_events() if isinstance(event, PromotionCreated)
    ]
    assert len(promotion_events) == 100


def test_short_horizon_does_not_clip_annual_pattern_duration() -> None:
    store = EventStore()
    ctx = SimulationContext(
        2,
        DateRange(date(2026, 1, 1), date(2026, 1, 1)),
        RandomEngine(2),
        EventBus(store),
    )
    bootstrap_dependencies(ctx)
    PromotionBootstrapGenerator(
        PromotionGenerationConfig(count=1, min_duration_days=5)
    ).generate(ctx)
    promotion = ctx.state.collection("promotions").all()[0]
    assert isinstance(promotion, Promotion)
    assert (promotion.end_date - promotion.start_date).days + 1 >= 5
    assert promotion.start_date.year == 2000


def test_promotion_reproducibility_and_duplicate_execution() -> None:
    pairs = [context(seed) for seed in (42, 42, 43)]
    for ctx, _ in pairs:
        bootstrap_dependencies(ctx)
        PromotionBootstrapGenerator(PromotionGenerationConfig()).generate(ctx)
    snapshots = [ctx.state.collection("promotions").all() for ctx, _ in pairs]
    assert snapshots[0] == snapshots[1] and snapshots[0] != snapshots[2]
    with pytest.raises(ValueError, match="must be empty"):
        PromotionBootstrapGenerator(PromotionGenerationConfig()).generate(pairs[0][0])


def test_missing_dependencies_fail_in_explicit_order() -> None:
    ctx, _ = context()
    generator: BootstrapGenerator = PromotionBootstrapGenerator(
        PromotionGenerationConfig(count=1)
    )
    with pytest.raises(ValueError, match="missing: regions"):
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
            PromotionBootstrapGenerator(PromotionGenerationConfig(count=20)),
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
        "promotions",
    )
    assert summary.generators_executed == 5
    assert summary.collections_created == 10
