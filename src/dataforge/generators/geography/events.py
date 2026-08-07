"""Events published while bootstrapping geography."""

from dataforge.core.events.event import DomainEvent
from dataforge.generators.geography.models import (
    AdministrativeArea,
    City,
    Country,
    Location,
    Region,
)


class CountryCreated(DomainEvent):
    def __init__(self, country: Country) -> None:
        super().__init__(
            event_type="CountryCreated",
            payload={
                "country_id": country.id,
                "code": country.code,
                "name": country.name,
            },
        )


class RegionCreated(DomainEvent):
    def __init__(self, region: Region) -> None:
        super().__init__(
            event_type="RegionCreated",
            payload={
                "region_id": region.id,
                "name": region.name,
                "country_id": region.country_id,
            },
        )


class AdministrativeAreaCreated(DomainEvent):
    def __init__(self, area: AdministrativeArea) -> None:
        super().__init__(
            event_type="AdministrativeAreaCreated",
            payload={
                "administrative_area_id": area.id,
                "name": area.name,
                "area_type": area.area_type,
                "region_id": area.region_id,
                "country_id": area.country_id,
            },
        )


class CityCreated(DomainEvent):
    def __init__(self, city: City) -> None:
        super().__init__(
            event_type="CityCreated",
            payload={
                "city_id": city.id,
                "name": city.name,
                "administrative_area_id": city.administrative_area_id,
                "region_id": city.region_id,
                "country_id": city.country_id,
            },
        )


class LocationCreated(DomainEvent):
    def __init__(self, location: Location) -> None:
        super().__init__(
            event_type="LocationCreated",
            payload={
                "location_id": location.id,
                "name": location.name,
                "city_id": location.city_id,
                "administrative_area_id": location.administrative_area_id,
                "region_id": location.region_id,
                "country_id": location.country_id,
                "capacity": location.capacity,
                "activity_factor": location.activity_factor,
                "opened_at": location.opened_at.isoformat(),
            },
        )
