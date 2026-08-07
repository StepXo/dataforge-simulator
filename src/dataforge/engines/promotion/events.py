"""Events published by the promotion engine."""

from dataforge.engines.promotion.models import PromotionContext
from dataforge.events.event import DomainEvent


class PromotionContextGenerated(DomainEvent):
    """Record the active promotion context for one tick."""

    def __init__(self, promotion_context: PromotionContext) -> None:
        super().__init__(
            event_type="PromotionContextGenerated",
            payload={
                "tick_index": promotion_context.tick_index,
                "current_time": promotion_context.current_time.isoformat(),
                "active_promotions": [
                    {
                        "promotion_id": promotion.promotion_id,
                        "target_type": promotion.target_type.value,
                        "target_ids": list(promotion.target_ids),
                        "channel": promotion.channel.value,
                        "discount_rate": promotion.discount_rate,
                        "demand_lift": promotion.demand_lift,
                    }
                    for promotion in promotion_context.active_promotions
                ],
            },
        )
