"""Events published while bootstrapping customers."""

from dataforge.customers.models import Customer
from dataforge.events.event import DomainEvent


class CustomerCreated(DomainEvent):
    def __init__(self, customer: Customer) -> None:
        super().__init__(
            event_type="CustomerCreated",
            payload={
                "customer_id": customer.id,
                "home_city_id": customer.home_city_id,
                "home_region_id": customer.home_region_id,
                "preferred_location_id": customer.preferred_location_id,
                "segment": customer.segment.value,
                "purchase_frequency": customer.purchase_frequency,
                "preferred_channel": customer.preferred_channel.value,
                "promotion_sensitivity": customer.promotion_sensitivity,
                "activity_factor": customer.activity_factor,
                "registered_at": customer.registered_at.isoformat(),
                "active": customer.active,
            },
        )
