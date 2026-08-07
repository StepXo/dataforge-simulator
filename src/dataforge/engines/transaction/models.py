"""Immutable transaction outcomes and per-tick summary."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dataforge.customers.models import PreferredChannel

ZERO_MONEY = Decimal("0.00")


class TransactionStatus(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"


class RejectionReason(StrEnum):
    INSUFFICIENT_STOCK = "insufficient_stock"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    basket_id: str
    intent_id: str
    quote_intent_id: str
    customer_id: str
    location_id: str
    product_id: str
    channel: PreferredChannel
    quantity: int
    currency: str
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    applied_promotion_ids: tuple[str, ...]
    status: TransactionStatus
    rejection_reason: RejectionReason | None
    tick_index: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("quantity must be at least one")
        if any(
            amount < 0
            for amount in (
                self.unit_price,
                self.gross_amount,
                self.discount_amount,
                self.net_amount,
            )
        ):
            raise ValueError("Transaction monetary amounts must be non-negative")
        if (
            self.status is TransactionStatus.COMPLETED
            and self.rejection_reason is not None
        ):
            raise ValueError("Completed Transaction cannot have a rejection reason")
        if self.status is TransactionStatus.REJECTED and self.rejection_reason is None:
            raise ValueError("Rejected Transaction requires a rejection reason")


@dataclass(frozen=True, slots=True)
class TransactionContext:
    tick_index: int
    current_time: datetime
    transactions: tuple[Transaction, ...]
    completed_count: int
    rejected_count: int
    completed_units: int
    rejected_units: int
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    lost_sales_amount: Decimal

    def __post_init__(self) -> None:
        completed = tuple(
            item
            for item in self.transactions
            if item.status is TransactionStatus.COMPLETED
        )
        rejected = tuple(
            item
            for item in self.transactions
            if item.status is TransactionStatus.REJECTED
        )
        expected = (
            len(completed),
            len(rejected),
            sum(item.quantity for item in completed),
            sum(item.quantity for item in rejected),
            sum((item.gross_amount for item in completed), start=ZERO_MONEY),
            sum((item.discount_amount for item in completed), start=ZERO_MONEY),
            sum((item.net_amount for item in completed), start=ZERO_MONEY),
            sum((item.net_amount for item in rejected), start=ZERO_MONEY),
        )
        actual = (
            self.completed_count,
            self.rejected_count,
            self.completed_units,
            self.rejected_units,
            self.gross_amount,
            self.discount_amount,
            self.net_amount,
            self.lost_sales_amount,
        )
        if actual != expected:
            raise ValueError("TransactionContext totals are inconsistent")
