"""Commercial basket events published by the transaction engine."""

from dataforge.engines.transaction.models import Transaction, TransactionContext
from dataforge.events.event import DomainEvent


def _transaction_payload(transaction: Transaction) -> dict[str, object]:
    return {
        "transaction_id": transaction.id,
        "basket_id": transaction.basket_id,
        "customer_id": transaction.customer_id,
        "location_id": transaction.location_id,
        "channel": transaction.channel.value,
        "currency": transaction.currency,
        "status": transaction.status.value,
        "gross_amount": str(transaction.gross_amount),
        "discount_amount": str(transaction.discount_amount),
        "net_amount": str(transaction.net_amount),
        "lost_sales_amount": str(transaction.lost_sales_amount),
        "completed_units": transaction.completed_units,
        "rejected_units": transaction.rejected_units,
        "lines": [
            {
                "line_id": line.id,
                "intent_id": line.intent_id,
                "product_id": line.product_id,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price),
                "gross_amount": str(line.gross_amount),
                "discount_amount": str(line.discount_amount),
                "net_amount": str(line.net_amount),
                "applied_promotion_ids": list(line.applied_promotion_ids),
                "status": line.status.value,
                "rejection_reason": (
                    line.rejection_reason.value if line.rejection_reason else None
                ),
            }
            for line in transaction.lines
        ],
        "tick_index": transaction.tick_index,
        "occurred_at": transaction.occurred_at.isoformat(),
    }


class TransactionCompleted(DomainEvent):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__("TransactionCompleted", _transaction_payload(transaction))


class TransactionPartiallyCompleted(DomainEvent):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(
            "TransactionPartiallyCompleted", _transaction_payload(transaction)
        )


class TransactionRejected(DomainEvent):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__("TransactionRejected", _transaction_payload(transaction))


class TransactionContextGenerated(DomainEvent):
    def __init__(self, context: TransactionContext) -> None:
        super().__init__(
            "TransactionContextGenerated",
            {
                "tick_index": context.tick_index,
                "current_time": context.current_time.isoformat(),
                "total_transactions": context.total_transactions,
                "completed_transactions": context.completed_transactions,
                "partially_completed_transactions": (
                    context.partially_completed_transactions
                ),
                "rejected_transactions": context.rejected_transactions,
                "transaction_lines": context.transaction_lines,
                "completed_lines": context.completed_lines,
                "rejected_lines": context.rejected_lines,
                "completed_units": context.completed_units,
                "rejected_units": context.rejected_units,
                "gross_amount": str(context.gross_amount),
                "discount_amount": str(context.discount_amount),
                "net_amount": str(context.net_amount),
                "lost_sales_amount": str(context.lost_sales_amount),
            },
        )
