"""Events published by the pricing engine."""

from dataforge.engines.pricing.models import PricingContext
from dataforge.events.event import DomainEvent


class PricingContextGenerated(DomainEvent):
    """Record all price quotes generated for one tick."""

    def __init__(self, pricing: PricingContext) -> None:
        super().__init__(
            event_type="PricingContextGenerated",
            payload={
                "tick_index": pricing.tick_index,
                "current_time": pricing.current_time.isoformat(),
                "currency": pricing.currency,
                "total_gross_amount": str(pricing.total_gross_amount),
                "total_discount_amount": str(pricing.total_discount_amount),
                "total_net_amount": str(pricing.total_net_amount),
                "quotes": [
                    {
                        "intent_id": quote.intent_id,
                        "basket_id": quote.basket_id,
                        "customer_id": quote.customer_id,
                        "location_id": quote.location_id,
                        "product_id": quote.product_id,
                        "channel": quote.channel.value,
                        "quantity": quote.quantity,
                        "currency": quote.currency,
                        "unit_base_price": str(quote.unit_base_price),
                        "unit_discount_amount": str(quote.unit_discount_amount),
                        "unit_effective_price": str(quote.unit_effective_price),
                        "gross_amount": str(quote.gross_amount),
                        "discount_amount": str(quote.discount_amount),
                        "net_amount": str(quote.net_amount),
                        "applied_promotion_ids": list(quote.applied_promotion_ids),
                        "tick_index": quote.tick_index,
                    }
                    for quote in pricing.quotes
                ],
            },
        )
