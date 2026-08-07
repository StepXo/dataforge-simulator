"""Events published while bootstrapping promotions."""

from dataforge.events.event import DomainEvent
from dataforge.promotions.models import Promotion


class PromotionCreated(DomainEvent):
    def __init__(self, promotion: Promotion) -> None:
        super().__init__(
            event_type="PromotionCreated",
            payload={
                "promotion_id": promotion.id,
                "name": promotion.name,
                "start_date": promotion.start_date.isoformat(),
                "end_date": promotion.end_date.isoformat(),
                "target_type": promotion.target_type.value,
                "target_ids": list(promotion.target_ids),
                "channel": promotion.channel.value,
                "discount_rate": promotion.discount_rate,
                "demand_lift": promotion.demand_lift,
                "active": promotion.active,
            },
        )
