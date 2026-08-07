"""Immutable values produced by the promotion engine."""

from dataclasses import dataclass
from datetime import datetime

from dataforge.generators.promotions.models import PromotionChannel, PromotionTargetType


@dataclass(frozen=True, slots=True)
class ActivePromotion:
    promotion_id: str
    target_type: PromotionTargetType
    target_ids: tuple[str, ...]
    channel: PromotionChannel
    discount_rate: float
    demand_lift: float


@dataclass(frozen=True, slots=True)
class PromotionContext:
    tick_index: int
    current_time: datetime
    active_promotions: tuple[ActivePromotion, ...]
