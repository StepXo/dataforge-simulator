"""Bootstrap generator for geographic state and synthetic locations."""

from datetime import date, timedelta
from typing import Self

from pydantic import BaseModel, Field, model_validator

from dataforge.bootstrap.collections import prepare_empty_collections
from dataforge.config.geography.models import GeographyDefinition
from dataforge.core.simulation_context import SimulationContext
from dataforge.generators.geography.events import (
    AdministrativeAreaCreated,
    CityCreated,
    CountryCreated,
    LocationCreated,
    RegionCreated,
)
from dataforge.generators.geography.models import (
    AdministrativeArea,
    City,
    Country,
    Location,
    Region,
)

COLLECTION_NAMES = (
    "countries",
    "regions",
    "administrative_areas",
    "cities",
    "locations",
)
LOCATION_SUFFIXES = ("Central", "North", "South", "East", "West")


class LocationGenerationConfig(BaseModel):
    """Validate the bounds used to synthesize operational locations."""

    min_per_region: int = Field(default=2, ge=1)
    max_per_region: int = 3
    min_capacity: int = Field(default=50, ge=1)
    max_capacity: int = 250
    min_activity_factor: float = Field(default=0.50, gt=0)
    max_activity_factor: float = 1.50

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.max_per_region < self.min_per_region:
            raise ValueError("max_per_region must be at least min_per_region")
        if self.max_capacity < self.min_capacity:
            raise ValueError("max_capacity must be at least min_capacity")
        if self.max_activity_factor < self.min_activity_factor:
            raise ValueError("max_activity_factor must be at least min_activity_factor")
        return self


class GeographyGenerator:
    """Convert geography definitions and synthesize locations during bootstrap."""

    def __init__(
        self,
        geography: GeographyDefinition,
        location_config: LocationGenerationConfig,
    ) -> None:
        self._geography = geography
        self._location_config = location_config

    def generate(self, context: SimulationContext) -> None:
        """Populate geographic state in deterministic dependency order."""
        prepare_empty_collections(context.state, COLLECTION_NAMES)
        country = self._create_country(context)
        regions = self._create_regions(context, country)
        areas = self._create_administrative_areas(context, country, regions)
        cities = self._create_cities(context, country, regions, areas)
        self._create_locations(context, country, regions, areas, cities)

    def _create_country(self, context: SimulationContext) -> Country:
        definition = self._geography.country
        country = Country(
            id=f"country-{definition.code.lower()}",
            code=definition.code,
            name=definition.name,
        )
        context.state.collection("countries").add(country.id, country)
        context.event_bus.publish(CountryCreated(country))
        return country

    def _create_regions(
        self,
        context: SimulationContext,
        country: Country,
    ) -> dict[str, Region]:
        regions: dict[str, Region] = {}
        collection = context.state.collection("regions")
        for definition in self._geography.regions:
            region = Region(
                id=f"region-{definition.id}",
                name=definition.name,
                country_id=country.id,
            )
            collection.add(region.id, region)
            context.event_bus.publish(RegionCreated(region))
            regions[definition.id] = region
        return regions

    def _create_administrative_areas(
        self,
        context: SimulationContext,
        country: Country,
        regions: dict[str, Region],
    ) -> dict[str, AdministrativeArea]:
        areas: dict[str, AdministrativeArea] = {}
        collection = context.state.collection("administrative_areas")
        for definition in self._geography.administrative_areas:
            region = regions.get(definition.region_id)
            if region is None:
                raise ValueError(f"Unknown region: {definition.region_id}")
            area = AdministrativeArea(
                id=f"administrative-area-{definition.id}",
                name=definition.name,
                area_type=definition.type,
                region_id=region.id,
                country_id=country.id,
            )
            collection.add(area.id, area)
            context.event_bus.publish(AdministrativeAreaCreated(area))
            areas[definition.id] = area
        return areas

    def _create_cities(
        self,
        context: SimulationContext,
        country: Country,
        regions: dict[str, Region],
        areas: dict[str, AdministrativeArea],
    ) -> dict[str, City]:
        cities: dict[str, City] = {}
        collection = context.state.collection("cities")
        for definition in self._geography.cities:
            area = areas.get(definition.administrative_area_id)
            if area is None:
                raise ValueError(
                    f"Unknown administrative area: {definition.administrative_area_id}"
                )
            if area.region_id not in {region.id for region in regions.values()}:
                raise ValueError(f"Unknown region for administrative area: {area.id}")
            city = City(
                id=f"city-{definition.id}",
                name=definition.name,
                administrative_area_id=area.id,
                region_id=area.region_id,
                country_id=country.id,
            )
            collection.add(city.id, city)
            context.event_bus.publish(CityCreated(city))
            cities[definition.id] = city
        return cities

    def _create_locations(
        self,
        context: SimulationContext,
        country: Country,
        regions: dict[str, Region],
        areas: dict[str, AdministrativeArea],
        cities: dict[str, City],
    ) -> None:
        collection = context.state.collection("locations")
        used_suffixes: dict[str, set[str]] = {}

        for definition in self._geography.regions:
            region = regions[definition.id]
            region_cities = [
                city for city in cities.values() if city.region_id == region.id
            ]
            if not region_cities:
                raise ValueError(f"Region has no cities: {definition.id}")

            location_count = context.random_engine.randint(
                self._location_config.min_per_region,
                self._location_config.max_per_region,
            )
            for sequence in range(1, location_count + 1):
                eligible_cities = [
                    city
                    for city in region_cities
                    if len(used_suffixes.get(city.id, set())) < len(LOCATION_SUFFIXES)
                ]
                if not eligible_cities:
                    raise ValueError(
                        f"No unique location names available in region: {region.id}"
                    )
                city = context.random_engine.choice(eligible_cities)
                area = next(
                    (
                        area
                        for area in areas.values()
                        if area.id == city.administrative_area_id
                    ),
                    None,
                )
                if (
                    area is None
                    or area.region_id != region.id
                    or region.country_id != country.id
                ):
                    raise ValueError(f"Incoherent geography for city: {city.id}")

                suffix = self._select_suffix(context, city, used_suffixes)
                location = Location(
                    id=f"location-{definition.id}-{sequence:03d}",
                    name=f"{city.name} {suffix}",
                    city_id=city.id,
                    administrative_area_id=area.id,
                    region_id=region.id,
                    country_id=country.id,
                    capacity=context.random_engine.randint(
                        self._location_config.min_capacity,
                        self._location_config.max_capacity,
                    ),
                    activity_factor=round(
                        context.random_engine.uniform(
                            self._location_config.min_activity_factor,
                            self._location_config.max_activity_factor,
                        ),
                        2,
                    ),
                    opened_at=self._opened_at(context),
                )
                collection.add(location.id, location)
                context.event_bus.publish(LocationCreated(location))

    def _select_suffix(
        self,
        context: SimulationContext,
        city: City,
        used_suffixes: dict[str, set[str]],
    ) -> str:
        used = used_suffixes.setdefault(city.id, set())
        selected = context.random_engine.choice(LOCATION_SUFFIXES)
        if selected in used:
            selected = next(
                suffix for suffix in LOCATION_SUFFIXES if suffix not in used
            )
        used.add(selected)
        return selected

    def _opened_at(self, context: SimulationContext) -> date:
        if context.random_engine.uniform(0.0, 1.0) < 0.70:
            earliest = _shift_year(context.date_range.start_date, -5)
            latest = _shift_year(context.date_range.start_date, -1)
        else:
            earliest = _shift_year(context.date_range.start_date, -1)
            latest = context.date_range.start_date
        offset = context.random_engine.randint(0, (latest - earliest).days)
        return earliest + timedelta(days=offset)


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)
