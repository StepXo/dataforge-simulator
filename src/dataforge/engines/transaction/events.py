"""Commercial events published by the transaction engine."""

from dataforge.engines.transaction.models import Transaction, TransactionContext
from dataforge.events.event import DomainEvent


def _transaction_payload(transaction: Transaction) -> dict[str, object]:
    return {
        "transaction_id": transaction.id,
        "basket_id": transaction.basket_id,
        "intent_id": transaction.intent_id,
        "customer_id": transaction.customer_id,
        "location_id": transaction.location_id,
        "product_id": transaction.product_id,
        "channel": transaction.channel.value,
        "quantity": transaction.quantity,
        "currency": transaction.currency,
        "unit_price": str(transaction.unit_price),
        "gross_amount": str(transaction.gross_amount),
        "discount_amount": str(transaction.discount_amount),
        "net_amount": str(transaction.net_amount),
        "applied_promotion_ids": list(transaction.applied_promotion_ids),
        "tick_index": transaction.tick_index,
        "occurred_at": transaction.occurred_at.isoformat(),
    }


class TransactionCompleted(DomainEvent):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(
            event_type="TransactionCompleted", payload=_transaction_payload(transaction)
        )


class TransactionRejected(DomainEvent):
    def __init__(self, transaction: Transaction) -> None:
        payload = _transaction_payload(transaction)
        payload["rejection_reason"] = (
            transaction.rejection_reason.value if transaction.rejection_reason else None
        )
        super().__init__(event_type="TransactionRejected", payload=payload)


class TransactionContextGenerated(DomainEvent):
    def __init__(self, context: TransactionContext) -> None:
        super().__init__(
            event_type="TransactionContextGenerated",
            payload={
                "tick_index": context.tick_index,
                "current_time": context.current_time.isoformat(),
                "completed_count": context.completed_count,
                "rejected_count": context.rejected_count,
                "completed_units": context.completed_units,
                "rejected_units": context.rejected_units,
                "gross_amount": str(context.gross_amount),
                "discount_amount": str(context.discount_amount),
                "net_amount": str(context.net_amount),
                "lost_sales_amount": str(context.lost_sales_amount),
            },
        )
