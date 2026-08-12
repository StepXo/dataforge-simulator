"""Immutable customer state models."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class CustomerSegment(StrEnum):
    OCCASIONAL = "occasional"
    REGULAR = "regular"
    FREQUENT = "frequent"
    INACTIVE = "inactive"


class PreferredChannel(StrEnum):
    PHYSICAL = "physical"
    MOBILE = "mobile"


@dataclass(frozen=True, slots=True)
class Customer:
    id: str
    home_city_id: str
    home_region_id: str
    preferred_location_id: str
    segment: CustomerSegment
    purchase_frequency: float
    preferred_channel: PreferredChannel
    promotion_sensitivity: float
    activity_factor: float
    registered_at: date
    active: bool
    activity_profile: str | None = None
