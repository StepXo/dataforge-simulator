"""Immutable promotion state models."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class PromotionTargetType(StrEnum):
    GLOBAL = "global"
    REGION = "region"
    LOCATION = "location"
    CATEGORY = "category"
    PRODUCT = "product"


class PromotionChannel(StrEnum):
    ALL = "all"
    PHYSICAL = "physical"
    MOBILE = "mobile"


@dataclass(frozen=True, slots=True)
class Promotion:
    id: str
    name: str
    start_date: date
    end_date: date
    target_type: PromotionTargetType
    target_ids: tuple[str, ...]
    channel: PromotionChannel
    discount_rate: float
    demand_lift: float
    active: bool
