"""Tests for geography bootstrap generation."""

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from dataforge.bootstrap.contracts import BootstrapGenerator
from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.configuration.geography import load_geography
from dataforge.configuration.geography.models import (
    CountryDefinition,
    GeographyDefinition,
    RegionDefinition,
)
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.events.event import DomainEvent
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.geography.generator import GeographyGenerator, LocationGenerationConfig
from dataforge.geography.models import AdministrativeArea, City, Country, Location

PATH = Path("configs/geography/colombia.yaml")
NAMES = ("countries", "regions", "administrative_areas", "cities", "locations")


def context(seed: int = 42) -> tuple[SimulationContext, EventStore]:
    store = EventStore()
    return SimulationContext(
        seed,
        DateRange(date(2026, 1, 1), date(2026, 12, 31)),
        RandomEngine(seed),
        EventBus(store),
    ), store


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_per_region": 0},
        {"min_per_region": 3, "max_per_region": 2},
        {"min_capacity": 0},
        {"min_capacity": 2, "max_capacity": 1},
        {"min_activity_factor": 0},
        {"min_activity_factor": 2.0, "max_activity_factor": 1.0},
    ],
)
def test_location_generation_config_bounds(kwargs: dict[str, int | float]) -> None:
    with pytest.raises(ValidationError):
        LocationGenerationConfig(**kwargs)


def test_location_generation_and_conversion() -> None:
    geography = load_geography(PATH)
    ctx, _ = context()
    GeographyGenerator(geography, LocationGenerationConfig()).generate(ctx)
    assert ctx.state.collection_names() == NAMES
    assert ctx.state.collection("regions").count() == len(geography.regions)
    assert ctx.state.collection("cities").count() == len(geography.cities)
    country = ctx.state.collection("countries").all()[0]
    assert country == Country("country-co", "CO", "Colombia")
    with pytest.raises(FrozenInstanceError):
        country.name = "changed"  # type: ignore[attr-defined]
    cities = {
        x.id: x for x in ctx.state.collection("cities").all() if isinstance(x, City)
    }
    areas = {
        x.id: x
        for x in ctx.state.collection("administrative_areas").all()
        if isinstance(x, AdministrativeArea)
    }
    locations = [
        x for x in ctx.state.collection("locations").all() if isinstance(x, Location)
    ]
    counts: dict[str, int] = {}
    names: dict[str, set[str]] = {}
    for item in locations:
        city, area = cities[item.city_id], areas[item.administrative_area_id]
        assert city.administrative_area_id == area.id
        assert city.region_id == area.region_id == item.region_id
        assert city.country_id == area.country_id == item.country_id
        assert 50 <= item.capacity <= 250 and 0.5 <= item.activity_factor <= 1.5
        assert date(2021, 1, 1) <= item.opened_at <= ctx.date_range.start_date
        counts[item.region_id] = counts.get(item.region_id, 0) + 1
        assert item.name not in names.setdefault(item.city_id, set())
        names[item.city_id].add(item.name)
    assert len(counts) == len(geography.regions)
    assert all(2 <= value <= 3 for value in counts.values())
    assert len({item.id for item in locations}) == len(locations)


def test_reproducible_events_duplicate_and_runner() -> None:
    geography = load_geography(PATH)
    contexts = [context(seed) for seed in (42, 42, 43)]
    fields = {
        "CountryCreated": ("countries", "country_id"),
        "RegionCreated": ("regions", "region_id"),
        "AdministrativeAreaCreated": ("administrative_areas", "administrative_area_id"),
        "CityCreated": ("cities", "city_id"),
        "LocationCreated": ("locations", "location_id"),
    }

    def subscribe(ctx: SimulationContext) -> None:
        def handler(event: DomainEvent) -> None:
            collection, field = fields[event.event_type]
            identifier = event.payload[field]
            assert isinstance(identifier, str)
            assert ctx.state.collection(collection).contains(identifier)

        for event_type in fields:
            ctx.event_bus.subscribe(event_type, handler)

    for ctx, _ in contexts:
        subscribe(ctx)
        GeographyGenerator(geography, LocationGenerationConfig()).generate(ctx)
    snapshots = [
        [ctx.state.collection(name).all() for name in NAMES] for ctx, _ in contexts
    ]
    assert snapshots[0] == snapshots[1] and snapshots[0][-1] != snapshots[2][-1]
    ctx, store = contexts[0]
    assert store.count() == ctx.state.total_records
    assert all(
        isinstance(e.payload["opened_at"], str)
        for e in store.all_events()
        if e.event_type == "LocationCreated"
    )
    with pytest.raises(ValueError, match="must be empty"):
        GeographyGenerator(geography, LocationGenerationConfig()).generate(ctx)
    runner_ctx, _ = context()
    generator: BootstrapGenerator = GeographyGenerator(
        geography, LocationGenerationConfig()
    )
    summary = BootstrapRunner([generator]).run(runner_ctx)
    assert (summary.generators_executed, summary.collections_created) == (1, 5)
    assert summary.records_created == runner_ctx.state.total_records


def test_empty_collections_reused_and_region_without_city_fails() -> None:
    ctx, _ = context()
    existing = {name: ctx.state.create_collection(name) for name in NAMES}
    GeographyGenerator(load_geography(PATH), LocationGenerationConfig()).generate(ctx)
    assert all(ctx.state.collection(name) is existing[name] for name in NAMES)
    invalid = GeographyDefinition(
        country=CountryDefinition(code="TS", name="Test"),
        regions=[RegionDefinition(id="empty", name="Empty")],
        administrative_areas=[],
        cities=[],
    )
    empty_ctx, _ = context()
    with pytest.raises(ValueError, match="Region has no cities: empty"):
        GeographyGenerator(invalid, LocationGenerationConfig()).generate(empty_ctx)
