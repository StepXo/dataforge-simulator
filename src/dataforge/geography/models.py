"""Immutable geographic entities used in simulation state."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Country:
    id: str
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class Region:
    id: str
    name: str
    country_id: str


@dataclass(frozen=True, slots=True)
class AdministrativeArea:
    id: str
    name: str
    area_type: str
    region_id: str
    country_id: str


@dataclass(frozen=True, slots=True)
class City:
    id: str
    name: str
    administrative_area_id: str
    region_id: str
    country_id: str


@dataclass(frozen=True, slots=True)
class Location:
    id: str
    name: str
    city_id: str
    administrative_area_id: str
    region_id: str
    country_id: str
    capacity: int
    activity_factor: float
    opened_at: date
