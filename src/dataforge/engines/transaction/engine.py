"""Resolve line outcomes and aggregate one transaction per basket."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.customer_behavior.models import (
    CustomerBehaviorContext,
    PurchaseIntent,
)
from dataforge.engines.pricing.models import PriceQuote, PricingContext
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.events import (
    TransactionCompleted,
    TransactionContextGenerated,
    TransactionPartiallyCompleted,
    TransactionRejected,
)
from dataforge.engines.transaction.models import (
    ZERO_MONEY,
    RejectionReason,
    Transaction,
    TransactionContext,
    TransactionLine,
    TransactionLineStatus,
    TransactionStatus,
)
from dataforge.generators.customers.models import Customer
from dataforge.generators.geography.models import Location
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Product

TRANSACTION_CONTEXT_COLLECTION = "transaction_context"


class TransactionEngine:
    """Resolve line-level all-or-nothing outcomes with a per-tick stock ledger."""

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
                    "Multiple active InventoryItems exist for commercial "
                    f"combination: {item.location_id}/{item.product_id}"
                )
            active_inventory[key] = item
        available_stock = {
            key: item.current_stock for key, item in active_inventory.items()
        }

        basket_lines: dict[str, list[TransactionLine]] = {}
        basket_metadata: dict[str, PurchaseIntent] = {}
        basket_currency: dict[str, str] = {}
        for line_sequence, intent in enumerate(behavior.intents, start=1):
            quote = quotes.get(intent.id)
            if quote is None:
                raise ValueError(
                    f"PriceQuote is missing for PurchaseIntent: {intent.id}"
                )
            self._validate_identity(intent, quote)
            self._validate_master(intent, customers, locations, products, temporal)
            first = basket_metadata.setdefault(intent.basket_id, intent)
            if (
                first.customer_id != intent.customer_id
                or first.location_id != intent.location_id
                or first.channel is not intent.channel
                or first.demand_tick_index != intent.demand_tick_index
            ):
                raise ValueError(f"Inconsistent basket metadata: {intent.basket_id}")
            currency = basket_currency.setdefault(intent.basket_id, quote.currency)
            if currency != quote.currency:
                raise ValueError(f"Inconsistent basket currency: {intent.basket_id}")

            key = (intent.location_id, intent.product_id)
            if key not in active_inventory:
                status = TransactionLineStatus.REJECTED
                reason = RejectionReason.INVENTORY_UNAVAILABLE
            elif available_stock[key] < intent.requested_quantity:
                status = TransactionLineStatus.REJECTED
                reason = RejectionReason.INSUFFICIENT_STOCK
            else:
                status = TransactionLineStatus.COMPLETED
                reason = None
                available_stock[key] -= intent.requested_quantity
            basket_lines.setdefault(intent.basket_id, []).append(
                TransactionLine(
                    id=f"transaction-line-{clock.tick_index}-{line_sequence:06d}",
                    intent_id=intent.id,
                    quote_intent_id=quote.intent_id,
                    product_id=intent.product_id,
                    quantity=intent.requested_quantity,
                    unit_price=quote.unit_effective_price,
                    gross_amount=quote.gross_amount,
                    discount_amount=quote.discount_amount,
                    net_amount=quote.net_amount,
                    applied_promotion_ids=quote.applied_promotion_ids,
                    status=status,
                    rejection_reason=reason,
                )
            )

        transactions = tuple(
            self._transaction(
                sequence,
                basket_id,
                basket_metadata[basket_id],
                basket_currency[basket_id],
                tuple(lines),
                clock.tick_index,
                temporal,
            )
            for sequence, (basket_id, lines) in enumerate(basket_lines.items(), start=1)
        )
        result = self._context(clock.tick_index, temporal, transactions)
        collection = (
            context.state.collection(TRANSACTION_CONTEXT_COLLECTION)
            if context.state.has_collection(TRANSACTION_CONTEXT_COLLECTION)
            else context.state.create_collection(TRANSACTION_CONTEXT_COLLECTION)
        )
        collection.add(f"tick-{clock.tick_index}", result)
        for transaction in result.transactions:
            event = (
                TransactionCompleted(transaction)
                if transaction.status is TransactionStatus.COMPLETED
                else TransactionPartiallyCompleted(transaction)
                if transaction.status is TransactionStatus.PARTIALLY_COMPLETED
                else TransactionRejected(transaction)
            )
            context.event_bus.publish(event)
        context.event_bus.publish(TransactionContextGenerated(result))

    def _transaction(
        self,
        sequence: int,
        basket_id: str,
        intent: PurchaseIntent,
        currency: str,
        lines: tuple[TransactionLine, ...],
        tick: int,
        temporal: TemporalContext,
    ) -> Transaction:
        completed = tuple(
            line for line in lines if line.status is TransactionLineStatus.COMPLETED
        )
        rejected = tuple(
            line for line in lines if line.status is TransactionLineStatus.REJECTED
        )
        status = (
            TransactionStatus.COMPLETED
            if not rejected
            else TransactionStatus.REJECTED
            if not completed
            else TransactionStatus.PARTIALLY_COMPLETED
        )
        return Transaction(
            id=f"transaction-{tick}-{sequence:06d}",
            basket_id=basket_id,
            customer_id=intent.customer_id,
            location_id=intent.location_id,
            channel=intent.channel,
            lines=lines,
            currency=currency,
            gross_amount=sum(
                (line.gross_amount for line in completed), start=ZERO_MONEY
            ),
            discount_amount=sum(
                (line.discount_amount for line in completed), start=ZERO_MONEY
            ),
            net_amount=sum((line.net_amount for line in completed), start=ZERO_MONEY),
            lost_sales_amount=sum(
                (line.net_amount for line in rejected), start=ZERO_MONEY
            ),
            completed_units=sum(line.quantity for line in completed),
            rejected_units=sum(line.quantity for line in rejected),
            status=status,
            tick_index=tick,
            occurred_at=temporal.current_time,
        )

    def _context(
        self,
        tick: int,
        temporal: TemporalContext,
        transactions: tuple[Transaction, ...],
    ) -> TransactionContext:
        lines = tuple(line for item in transactions for line in item.lines)
        return TransactionContext(
            tick,
            temporal.current_time,
            transactions,
            len(transactions),
            sum(item.status is TransactionStatus.COMPLETED for item in transactions),
            sum(
                item.status is TransactionStatus.PARTIALLY_COMPLETED
                for item in transactions
            ),
            sum(item.status is TransactionStatus.REJECTED for item in transactions),
            len(lines),
            sum(line.status is TransactionLineStatus.COMPLETED for line in lines),
            sum(line.status is TransactionLineStatus.REJECTED for line in lines),
            sum(item.completed_units for item in transactions),
            sum(item.rejected_units for item in transactions),
            sum((item.gross_amount for item in transactions), start=ZERO_MONEY),
            sum((item.discount_amount for item in transactions), start=ZERO_MONEY),
            sum((item.net_amount for item in transactions), start=ZERO_MONEY),
            sum((item.lost_sales_amount for item in transactions), start=ZERO_MONEY),
        )

    def _validate_master(
        self,
        intent: PurchaseIntent,
        customers: dict[str, Customer],
        locations: dict[str, Location],
        products: dict[str, Product],
        temporal: TemporalContext,
    ) -> None:
        if intent.customer_id not in customers:
            raise ValueError(f"PurchaseIntent references unknown Customer: {intent.id}")
        location = locations.get(intent.location_id)
        if location is None:
            raise ValueError(f"PurchaseIntent references unknown Location: {intent.id}")
        if location.opened_at > temporal.current_time.date():
            raise ValueError(
                f"PurchaseIntent references unopened Location: {intent.id}"
            )
        product = products.get(intent.product_id)
        if product is None or not product.active:
            raise ValueError(
                f"PurchaseIntent references unavailable Product: {intent.id}"
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
