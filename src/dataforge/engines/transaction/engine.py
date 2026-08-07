"""Engine that decides transaction outcomes without mutating inventory."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.customers.models import Customer
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.pricing.models import PriceQuote, PricingContext
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.events import (
    TransactionCompleted,
    TransactionContextGenerated,
    TransactionRejected,
)
from dataforge.engines.transaction.models import (
    ZERO_MONEY,
    RejectionReason,
    Transaction,
    TransactionContext,
    TransactionStatus,
)
from dataforge.geography.models import Location
from dataforge.inventory.models import InventoryItem
from dataforge.products.models import Product

TRANSACTION_CONTEXT_COLLECTION = "transaction_context"


class TransactionEngine:
    """Resolve all-or-nothing outcomes using a local per-tick stock ledger."""

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        customers = {
            item.id: item
            for item in self._typed_collection(context, "customers", Customer)
        }
        locations = {
            item.id: item
            for item in self._typed_collection(context, "locations", Location)
        }
        products = {
            item.id: item
            for item in self._typed_collection(context, "products", Product)
        }
        inventory = self._typed_collection(context, "inventory", InventoryItem)
        temporal = self._tick_context(
            context, "temporal_context", clock.tick_index, TemporalContext
        )
        behavior = self._tick_context(
            context,
            "customer_behavior_context",
            clock.tick_index,
            CustomerBehaviorContext,
        )
        pricing = self._tick_context(
            context, "pricing_context", clock.tick_index, PricingContext
        )
        quotes = self._quotes_by_intent(pricing.quotes)
        if len(quotes) != len(behavior.intents):
            raise ValueError("PricingContext must contain exactly one quote per intent")

        active_inventory: dict[tuple[str, str], InventoryItem] = {}
        for item in inventory:
            if not item.active:
                continue
            key = (item.location_id, item.product_id)
            if key in active_inventory:
                raise ValueError(
                    "Multiple active InventoryItems exist for commercial combination: "
                    f"{item.location_id}/{item.product_id}"
                )
            active_inventory[key] = item
        available_stock = {
            key: item.current_stock for key, item in active_inventory.items()
        }

        transactions: list[Transaction] = []
        for sequence, intent in enumerate(behavior.intents, start=1):
            quote = quotes.get(intent.id)
            if quote is None:
                raise ValueError(
                    f"PriceQuote is missing for PurchaseIntent: {intent.id}"
                )
            self._validate_identity(intent, quote)
            if intent.customer_id not in customers:
                raise ValueError(
                    f"PurchaseIntent references unknown Customer: {intent.id}"
                )
            location = locations.get(intent.location_id)
            if location is None:
                raise ValueError(
                    f"PurchaseIntent references unknown Location: {intent.id}"
                )
            if location.opened_at > temporal.current_time.date():
                raise ValueError(
                    f"PurchaseIntent references unopened Location: {intent.id}"
                )
            product = products.get(intent.product_id)
            if product is None or not product.active:
                raise ValueError(
                    f"PurchaseIntent references unavailable Product: {intent.id}"
                )

            key = (intent.location_id, intent.product_id)
            if key not in active_inventory:
                status = TransactionStatus.REJECTED
                reason = RejectionReason.INVENTORY_UNAVAILABLE
            elif available_stock[key] < intent.requested_quantity:
                status = TransactionStatus.REJECTED
                reason = RejectionReason.INSUFFICIENT_STOCK
            else:
                status = TransactionStatus.COMPLETED
                reason = None
                available_stock[key] -= intent.requested_quantity
            transactions.append(
                Transaction(
                    id=f"transaction-{clock.tick_index}-{sequence:06d}",
                    basket_id=intent.basket_id,
                    intent_id=intent.id,
                    quote_intent_id=quote.intent_id,
                    customer_id=intent.customer_id,
                    location_id=intent.location_id,
                    product_id=intent.product_id,
                    channel=intent.channel,
                    quantity=intent.requested_quantity,
                    currency=quote.currency,
                    unit_price=quote.unit_effective_price,
                    gross_amount=quote.gross_amount,
                    discount_amount=quote.discount_amount,
                    net_amount=quote.net_amount,
                    applied_promotion_ids=quote.applied_promotion_ids,
                    status=status,
                    rejection_reason=reason,
                    tick_index=clock.tick_index,
                    occurred_at=temporal.current_time,
                )
            )

        result = self._context(clock.tick_index, temporal, tuple(transactions))
        if context.state.has_collection(TRANSACTION_CONTEXT_COLLECTION):
            collection = context.state.collection(TRANSACTION_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(TRANSACTION_CONTEXT_COLLECTION)
        collection.add(f"tick-{clock.tick_index}", result)
        for transaction in result.transactions:
            event = (
                TransactionCompleted(transaction)
                if transaction.status is TransactionStatus.COMPLETED
                else TransactionRejected(transaction)
            )
            context.event_bus.publish(event)
        context.event_bus.publish(TransactionContextGenerated(result))

    def _context(
        self,
        tick_index: int,
        temporal: TemporalContext,
        transactions: tuple[Transaction, ...],
    ) -> TransactionContext:
        completed = tuple(
            item for item in transactions if item.status is TransactionStatus.COMPLETED
        )
        rejected = tuple(
            item for item in transactions if item.status is TransactionStatus.REJECTED
        )
        return TransactionContext(
            tick_index=tick_index,
            current_time=temporal.current_time,
            transactions=transactions,
            completed_count=len(completed),
            rejected_count=len(rejected),
            completed_units=sum(item.quantity for item in completed),
            rejected_units=sum(item.quantity for item in rejected),
            gross_amount=sum(
                (item.gross_amount for item in completed), start=ZERO_MONEY
            ),
            discount_amount=sum(
                (item.discount_amount for item in completed), start=ZERO_MONEY
            ),
            net_amount=sum((item.net_amount for item in completed), start=ZERO_MONEY),
            lost_sales_amount=sum(
                (item.net_amount for item in rejected), start=ZERO_MONEY
            ),
        )

    def _quotes_by_intent(
        self, quotes: tuple[PriceQuote, ...]
    ) -> dict[str, PriceQuote]:
        result: dict[str, PriceQuote] = {}
        for quote in quotes:
            if quote.intent_id in result:
                raise ValueError(f"Duplicate PriceQuote for intent: {quote.intent_id}")
            result[quote.intent_id] = quote
        return result

    def _validate_identity(self, intent: PurchaseIntent, quote: PriceQuote) -> None:
        if (
            intent.basket_id != quote.basket_id
            or intent.customer_id != quote.customer_id
            or intent.location_id != quote.location_id
            or intent.product_id != quote.product_id
            or intent.channel is not quote.channel
            or intent.requested_quantity != quote.quantity
        ):
            raise ValueError(f"PriceQuote does not match PurchaseIntent: {intent.id}")

    def _typed_collection[T](
        self, context: SimulationContext, name: str, expected_type: type[T]
    ) -> tuple[T, ...]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required transaction collection is missing: {name}")
        values = context.state.collection(name).all()
        if not values:
            raise ValueError(f"Required transaction collection is empty: {name}")
        typed = tuple(value for value in values if isinstance(value, expected_type))
        if len(typed) != len(values):
            raise ValueError(f"Transaction dependency contains invalid records: {name}")
        return typed

    def _tick_context[T](
        self,
        context: SimulationContext,
        name: str,
        tick_index: int,
        expected_type: type[T],
    ) -> T:
        if not context.state.has_collection(name):
            raise ValueError(f"Required transaction collection is missing: {name}")
        value = context.state.collection(name).get(f"tick-{tick_index}")
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for tick: {tick_index}")
        return value
