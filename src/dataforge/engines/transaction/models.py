"""Immutable basket transactions, product lines, and per-tick summary."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dataforge.generators.customers.models import PreferredChannel

ZERO_MONEY = Decimal("0.00")


class TransactionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    REJECTED = "rejected"


class TransactionLineStatus(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"


class RejectionReason(StrEnum):
    INSUFFICIENT_STOCK = "insufficient_stock"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"


@dataclass(frozen=True, slots=True)
class TransactionLine:
    id: str
    intent_id: str
    quote_intent_id: str
    product_id: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    applied_promotion_ids: tuple[str, ...]
    status: TransactionLineStatus
    rejection_reason: RejectionReason | None

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("quantity must be at least one")
        amounts = (
            self.unit_price,
            self.gross_amount,
            self.discount_amount,
            self.net_amount,
        )
        if any(amount < 0 for amount in amounts):
            raise ValueError("TransactionLine monetary amounts must be non-negative")
        if self.unit_price * Decimal(self.quantity) != self.gross_amount:
            raise ValueError("TransactionLine gross amount is inconsistent")
        if self.gross_amount - self.discount_amount != self.net_amount:
            raise ValueError("TransactionLine net amount is inconsistent")
        if (self.status is TransactionLineStatus.COMPLETED) != (
            self.rejection_reason is None
        ):
            raise ValueError("TransactionLine status and rejection reason disagree")


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    basket_id: str
    customer_id: str
    location_id: str
    channel: PreferredChannel
    lines: tuple[TransactionLine, ...]
    currency: str
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    lost_sales_amount: Decimal
    completed_units: int
    rejected_units: int
    status: TransactionStatus
    tick_index: int
    occurred_at: datetime

    @property
    def intent_id(self) -> str:
        return self._single_line().intent_id

    @property
    def quote_intent_id(self) -> str:
        return self._single_line().quote_intent_id

    @property
    def product_id(self) -> str:
        return self._single_line().product_id

    @property
    def quantity(self) -> int:
        return self._single_line().quantity

    @property
    def unit_price(self) -> Decimal:
        return self._single_line().unit_price

    @property
    def applied_promotion_ids(self) -> tuple[str, ...]:
        return self._single_line().applied_promotion_ids

    @property
    def rejection_reason(self) -> RejectionReason | None:
        return self._single_line().rejection_reason

    def _single_line(self) -> TransactionLine:
        if len(self.lines) != 1:
            raise AttributeError("Basket transaction contains multiple lines")
        return self.lines[0]

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("Transaction requires at least one line")
        completed = tuple(
            line
            for line in self.lines
            if line.status is TransactionLineStatus.COMPLETED
        )
        rejected = tuple(
            line for line in self.lines if line.status is TransactionLineStatus.REJECTED
        )
        expected_status = (
            TransactionStatus.COMPLETED
            if not rejected
            else TransactionStatus.REJECTED
            if not completed
            else TransactionStatus.PARTIALLY_COMPLETED
        )
        expected = (
            sum((line.gross_amount for line in completed), start=ZERO_MONEY),
            sum((line.discount_amount for line in completed), start=ZERO_MONEY),
            sum((line.net_amount for line in completed), start=ZERO_MONEY),
            sum((line.net_amount for line in rejected), start=ZERO_MONEY),
            sum(line.quantity for line in completed),
            sum(line.quantity for line in rejected),
            expected_status,
        )
        actual = (
            self.gross_amount,
            self.discount_amount,
            self.net_amount,
            self.lost_sales_amount,
            self.completed_units,
            self.rejected_units,
            self.status,
        )
        if actual != expected:
            raise ValueError("Transaction basket totals are inconsistent")


@dataclass(frozen=True, slots=True)
class TransactionContext:
    tick_index: int
    current_time: datetime
    transactions: tuple[Transaction, ...]
    total_transactions: int
    completed_transactions: int
    partially_completed_transactions: int
    rejected_transactions: int
    transaction_lines: int
    completed_lines: int
    rejected_lines: int
    completed_units: int
    rejected_units: int
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    lost_sales_amount: Decimal

    @property
    def completed_count(self) -> int:
        """Backward-compatible alias for basket-level completed transactions."""
        return self.completed_transactions

    @property
    def rejected_count(self) -> int:
        """Backward-compatible alias for basket-level rejected transactions."""
        return self.rejected_transactions

    def __post_init__(self) -> None:
        lines = tuple(
            line for transaction in self.transactions for line in transaction.lines
        )
        expected = (
            len(self.transactions),
            sum(
                item.status is TransactionStatus.COMPLETED for item in self.transactions
            ),
            sum(
                item.status is TransactionStatus.PARTIALLY_COMPLETED
                for item in self.transactions
            ),
            sum(
                item.status is TransactionStatus.REJECTED for item in self.transactions
            ),
            len(lines),
            sum(line.status is TransactionLineStatus.COMPLETED for line in lines),
            sum(line.status is TransactionLineStatus.REJECTED for line in lines),
            sum(item.completed_units for item in self.transactions),
            sum(item.rejected_units for item in self.transactions),
            sum((item.gross_amount for item in self.transactions), start=ZERO_MONEY),
            sum((item.discount_amount for item in self.transactions), start=ZERO_MONEY),
            sum((item.net_amount for item in self.transactions), start=ZERO_MONEY),
            sum(
                (item.lost_sales_amount for item in self.transactions), start=ZERO_MONEY
            ),
        )
        actual = (
            self.total_transactions,
            self.completed_transactions,
            self.partially_completed_transactions,
            self.rejected_transactions,
            self.transaction_lines,
            self.completed_lines,
            self.rejected_lines,
            self.completed_units,
            self.rejected_units,
            self.gross_amount,
            self.discount_amount,
            self.net_amount,
            self.lost_sales_amount,
        )
        if actual != expected:
            raise ValueError("TransactionContext totals are inconsistent")
