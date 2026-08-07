"""Events published by the demand engine."""

from dataforge.engines.demand.models import DemandContext
from dataforge.events.event import DomainEvent


class DemandContextGenerated(DomainEvent):
    """Record potential aggregate demand for one tick."""

    def __init__(self, demand_context: DemandContext) -> None:
        super().__init__(
            event_type="DemandContextGenerated",
            payload={
                "tick_index": demand_context.tick_index,
                "current_time": demand_context.current_time.isoformat(),
                "total_requested_units": demand_context.total_requested_units,
                "demands": [
                    {
                        "location_id": demand.location_id,
                        "product_id": demand.product_id,
                        "expected_demand": demand.expected_demand,
                        "requested_units": demand.requested_units,
                    }
                    for demand in demand_context.demands
                ],
            },
        )
