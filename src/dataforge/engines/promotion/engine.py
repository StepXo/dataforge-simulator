"""Engine that interprets the promotion calendar for each tick."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.promotion.events import PromotionContextGenerated
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.models import TemporalContext
from dataforge.promotions.models import Promotion

PROMOTION_CONTEXT_COLLECTION = "promotion_context"
PROMOTIONS_COLLECTION = "promotions"
TEMPORAL_CONTEXT_COLLECTION = "temporal_context"


class PromotionEngine:
    """Store the promotions that are temporally active for each tick."""

    def execute(
        self,
        context: SimulationContext,
        clock: SimulationClock,
    ) -> None:
        """Interpret the current promotion calendar without advancing time."""
        promotions = self._promotions(context)
        temporal_context = self._temporal_context(context, clock.tick_index)
        current_date = temporal_context.current_time.date()
        active_promotions = tuple(
            ActivePromotion(
                promotion_id=promotion.id,
                target_type=promotion.target_type,
                target_ids=promotion.target_ids,
                channel=promotion.channel,
                discount_rate=promotion.discount_rate,
                demand_lift=promotion.demand_lift,
            )
            for promotion in promotions
            if promotion.active
            and promotion.start_date <= current_date <= promotion.end_date
        )
        promotion_context = PromotionContext(
            tick_index=clock.tick_index,
            current_time=temporal_context.current_time,
            active_promotions=active_promotions,
        )
        if context.state.has_collection(PROMOTION_CONTEXT_COLLECTION):
            collection = context.state.collection(PROMOTION_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(PROMOTION_CONTEXT_COLLECTION)
        collection.add(f"tick-{clock.tick_index}", promotion_context)
        context.event_bus.publish(PromotionContextGenerated(promotion_context))

    def _promotions(self, context: SimulationContext) -> tuple[Promotion, ...]:
        if not context.state.has_collection(PROMOTIONS_COLLECTION):
            raise ValueError("Required promotion collection is missing: promotions")
        values = context.state.collection(PROMOTIONS_COLLECTION).all()
        promotions = tuple(value for value in values if isinstance(value, Promotion))
        if len(promotions) != len(values):
            raise ValueError("Promotions collection contains invalid records")
        return promotions

    def _temporal_context(
        self,
        context: SimulationContext,
        tick_index: int,
    ) -> TemporalContext:
        if not context.state.has_collection(TEMPORAL_CONTEXT_COLLECTION):
            raise ValueError(
                "Required promotion collection is missing: temporal_context"
            )
        key = f"tick-{tick_index}"
        value = context.state.collection(TEMPORAL_CONTEXT_COLLECTION).get(key)
        if not isinstance(value, TemporalContext):
            raise ValueError(f"Temporal context is missing for tick: {tick_index}")
        return value
