"""Validated models for geography reference configuration."""

from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CountryCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=2),
]


class CountryDefinition(BaseModel):
    """Define a country by ISO-like two-character code and name."""

    code: CountryCode
    name: NonEmptyString

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        """Normalize string country codes to uppercase before validation."""
        if isinstance(value, str):
            return value.upper()
        return value


class RegionDefinition(BaseModel):
    """Define a named geographic region."""

    id: NonEmptyString
    name: NonEmptyString


class AdministrativeAreaDefinition(BaseModel):
    """Define an administrative area belonging to a region."""

    id: NonEmptyString
    name: NonEmptyString
    type: NonEmptyString
    region_id: NonEmptyString


class CityDefinition(BaseModel):
    """Define a city belonging to an administrative area."""

    id: NonEmptyString
    name: NonEmptyString
    administrative_area_id: NonEmptyString


class GeographyDefinition(BaseModel):
    """Define and validate one country's geographic reference hierarchy."""

    country: CountryDefinition
    regions: list[RegionDefinition]
    administrative_areas: list[AdministrativeAreaDefinition]
    cities: list[CityDefinition]

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        """Require unique IDs and valid parent references."""
        region_ids = [region.id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("Region IDs must be unique")

        administrative_area_ids = [area.id for area in self.administrative_areas]
        if len(administrative_area_ids) != len(set(administrative_area_ids)):
            raise ValueError("Administrative area IDs must be unique")

        city_ids = [city.id for city in self.cities]
        if len(city_ids) != len(set(city_ids)):
            raise ValueError("City IDs must be unique")

        known_region_ids = set(region_ids)
        for area in self.administrative_areas:
            if area.region_id not in known_region_ids:
                raise ValueError(
                    f"Administrative area {area.id} references unknown region "
                    f"{area.region_id}"
                )

        known_area_ids = set(administrative_area_ids)
        for city in self.cities:
            if city.administrative_area_id not in known_area_ids:
                raise ValueError(
                    f"City {city.id} references unknown administrative area "
                    f"{city.administrative_area_id}"
                )

        return self
