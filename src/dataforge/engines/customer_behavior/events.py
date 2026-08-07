"""Events published by the customer behavior engine."""

from dataforge.core.events.event import DomainEvent
from dataforge.engines.customer_behavior.models import CustomerBehaviorContext


class CustomerBehaviorContextGenerated(DomainEvent):
    """Record concrete purchase intentions generated for one tick."""

    def __init__(self, behavior_context: CustomerBehaviorContext) -> None:
        super().__init__(
            event_type="CustomerBehaviorContextGenerated",
            payload={
                "tick_index": behavior_context.tick_index,
                "current_time": behavior_context.current_time.isoformat(),
                "total_intents": behavior_context.total_intents,
                "total_requested_units": behavior_context.total_requested_units,
                "unassigned_demand_units": behavior_context.unassigned_demand_units,
                "intents": [
                    {
                        "id": intent.id,
                        "basket_id": intent.basket_id,
                        "customer_id": intent.customer_id,
                        "location_id": intent.location_id,
                        "product_id": intent.product_id,
                        "channel": intent.channel.value,
                        "requested_quantity": intent.requested_quantity,
                        "demand_tick_index": intent.demand_tick_index,
                    }
                    for intent in behavior_context.intents
                ],
            },
        )
