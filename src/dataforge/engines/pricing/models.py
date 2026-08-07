"""Immutable monetary results produced by the pricing engine."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from dataforge.customers.models import PreferredChannel

ZERO_MONEY = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class PriceQuote:
    intent_id: str
    basket_id: str
    customer_id: str
    location_id: str
    product_id: str
    channel: PreferredChannel
    quantity: int
    currency: str
    unit_base_price: Decimal
    unit_discount_amount: Decimal
    unit_effective_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    applied_promotion_ids: tuple[str, ...]
    tick_index: int

    def __post_init__(self) -> None:
        amounts = (
            self.unit_base_price,
            self.unit_discount_amount,
            self.unit_effective_price,
            self.gross_amount,
            self.discount_amount,
            self.net_amount,
        )
        if self.quantity < 1:
            raise ValueError("quantity must be at least one")
        if any(amount < 0 for amount in amounts):
            raise ValueError("PriceQuote monetary amounts must be non-negative")
        if (
            self.unit_base_price - self.unit_discount_amount
            != self.unit_effective_price
        ):
            raise ValueError("Unit price amounts are inconsistent")
        quantity = Decimal(self.quantity)
        if self.unit_base_price * quantity != self.gross_amount:
            raise ValueError("gross_amount is inconsistent")
        if self.unit_discount_amount * quantity != self.discount_amount:
            raise ValueError("discount_amount is inconsistent")
        if self.unit_effective_price * quantity != self.net_amount:
            raise ValueError("net_amount is inconsistent")
        if self.gross_amount - self.discount_amount != self.net_amount:
            raise ValueError("Quote totals are inconsistent")


@dataclass(frozen=True, slots=True)
class PricingContext:
    tick_index: int
    current_time: datetime
    currency: str | None
    quotes: tuple[PriceQuote, ...]
    total_gross_amount: Decimal
    total_discount_amount: Decimal
    total_net_amount: Decimal

    def __post_init__(self) -> None:
        currencies = {quote.currency for quote in self.quotes}
        expected_currency = next(iter(currencies)) if len(currencies) == 1 else None
        if len(currencies) > 1:
            raise ValueError("PricingContext cannot contain multiple currencies")
        if self.currency != expected_currency:
            raise ValueError("PricingContext currency is inconsistent with quotes")
        if self.total_gross_amount != sum(
            (quote.gross_amount for quote in self.quotes), start=ZERO_MONEY
        ):
            raise ValueError("total_gross_amount is inconsistent")
        if self.total_discount_amount != sum(
            (quote.discount_amount for quote in self.quotes), start=ZERO_MONEY
        ):
            raise ValueError("total_discount_amount is inconsistent")
        if self.total_net_amount != sum(
            (quote.net_amount for quote in self.quotes), start=ZERO_MONEY
        ):
            raise ValueError("total_net_amount is inconsistent")
