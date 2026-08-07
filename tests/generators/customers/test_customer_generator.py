"""Tests for customer bootstrap generation."""

from dataclasses import FrozenInstanceError
from datetime import date
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
from dataforge.generators.customers.events import CustomerCreated
from dataforge.generators.customers.generator import (
    CustomerGenerationConfig,
    CustomerGenerator,
)
from dataforge.generators.customers.models import (
    Customer,
    CustomerSegment,
    PreferredChannel,
)
from dataforge.generators.geography.generator import (
    GeographyGenerator,
    LocationGenerationConfig,
)
from dataforge.generators.geography.models import City, Location
from dataforge.generators.products.generator import ProductGenerator


def context(seed: int = 42) -> tuple[SimulationContext, EventStore]:
    store = EventStore()
    return SimulationContext(
        seed,
        DateRange(date(2026, 1, 1), date(2026, 12, 31)),
        RandomEngine(seed),
        EventBus(store),
    ), store


def bootstrap_geography(ctx: SimulationContext) -> None:
    GeographyGenerator(
        load_geography(Path("configs/geography/colombia.yaml")),
        LocationGenerationConfig(),
    ).generate(ctx)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"count": 0},
        {"min_purchase_frequency": -1},
        {"min_purchase_frequency": 2, "max_purchase_frequency": 1},
        {"mobile_preference_probability": -0.1},
        {"mobile_preference_probability": 1.1},
        {"inactive_probability": -0.1},
        {"inactive_probability": 1.1},
        {"high_frequency_probability": -0.1},
        {"high_frequency_probability": 1.1},
    ],
)
def test_customer_config_validation(kwargs: dict[str, int | float]) -> None:
    with pytest.raises(ValidationError):
        CustomerGenerationConfig(**kwargs)


def test_customer_is_immutable_and_preserves_enums() -> None:
    customer = Customer(
        "customer-000001",
        "city-a",
        "region-a",
        "location-a-001",
        CustomerSegment.REGULAR,
        2.4,
        PreferredChannel.MOBILE,
        0.7,
        1.1,
        date(2025, 1, 1),
        True,
    )
    assert customer.segment is CustomerSegment.REGULAR
    assert customer.preferred_channel is PreferredChannel.MOBILE
    with pytest.raises(FrozenInstanceError):
        customer.__setattr__("active", False)


def test_customer_generator_invariants_and_distribution() -> None:
    ctx, _ = context()
    bootstrap_geography(ctx)
    CustomerGenerator(CustomerGenerationConfig(count=500)).generate(ctx)

    cities = {
        value.id: value
        for value in ctx.state.collection("cities").all()
        if isinstance(value, City)
    }
    locations = {
        value.id: value
        for value in ctx.state.collection("locations").all()
        if isinstance(value, Location)
    }
    customers = [
        value
        for value in ctx.state.collection("customers").all()
        if isinstance(value, Customer)
    ]
    assert len(customers) == 500
    assert [item.id for item in customers] == [
        f"customer-{index:06d}" for index in range(1, 501)
    ]
    for item in customers:
        city, location = (
            cities[item.home_city_id],
            locations[item.preferred_location_id],
        )
        assert item.home_region_id == city.region_id == location.region_id
        if any(candidate.city_id == city.id for candidate in locations.values()):
            assert location.city_id == city.id
        assert 0 <= item.promotion_sensitivity <= 1
        assert 0.5 <= item.activity_factor <= 1.5
        assert item.registered_at <= ctx.date_range.start_date
        if item.segment is CustomerSegment.INACTIVE:
            assert item.purchase_frequency == 0 and item.active is False
        else:
            assert 0.2 <= item.purchase_frequency <= 8 and item.active is True
    assert len({item.segment for item in customers}) > 1
    assert len({item.preferred_channel for item in customers}) == 2
    assert len({item.purchase_frequency for item in customers}) > 1
    assert len({item.activity_factor for item in customers}) > 1


def test_preferred_location_falls_back_within_region() -> None:
    ctx, _ = context()
    bootstrap_geography(ctx)
    cities = [
        value
        for value in ctx.state.collection("cities").all()
        if isinstance(value, City)
    ]
    locations = [
        value
        for value in ctx.state.collection("locations").all()
        if isinstance(value, Location)
    ]
    city_without_location = next(
        city
        for city in cities
        if not any(location.city_id == city.id for location in locations)
    )
    ctx.state.collection("cities").clear()
    ctx.state.collection("cities").add(city_without_location.id, city_without_location)
    CustomerGenerator(CustomerGenerationConfig(count=20)).generate(ctx)
    assert all(
        isinstance(value, Customer)
        and value.home_region_id == city_without_location.region_id
        for value in ctx.state.collection("customers").all()
    )


def test_customer_reproducibility_events_duplicate_and_runner_order() -> None:
    pairs = [context(seed) for seed in (42, 42, 43)]
    for ctx, store in pairs:
        bootstrap_geography(ctx)
        before = store.count()

        def stored(event: DomainEvent, current: SimulationContext = ctx) -> None:
            identifier = event.payload["customer_id"]
            assert isinstance(identifier, str)
            assert current.state.collection("customers").contains(identifier)

        ctx.event_bus.subscribe("CustomerCreated", stored)
        CustomerGenerator(CustomerGenerationConfig(count=100)).generate(ctx)
        assert store.count() - before == 100
        assert all(
            isinstance(event, CustomerCreated) for event in store.all_events()[before:]
        )
    snapshots = [ctx.state.collection("customers").all() for ctx, _ in pairs]
    assert snapshots[0] == snapshots[1] and snapshots[0] != snapshots[2]
    with pytest.raises(ValueError, match="must be empty"):
        CustomerGenerator(CustomerGenerationConfig(count=1)).generate(pairs[0][0])

    missing, _ = context()
    generator: BootstrapGenerator = CustomerGenerator(CustomerGenerationConfig(count=1))
    with pytest.raises(ValueError, match="geography collection is missing"):
        BootstrapRunner([generator]).run(missing)


def test_complete_bootstrap_integration() -> None:
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
    )
    assert summary.generators_executed == 3
    assert summary.collections_created == 8
