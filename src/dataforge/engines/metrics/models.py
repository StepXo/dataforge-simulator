"""Immutable per-tick metrics snapshot."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MetricsContext:
    tick_index: int
    current_time: datetime
    demand_records: int
    demand_units: int
    purchase_intents: int
    intent_units: int
    unassigned_demand_units: int
    price_quotes: int
    total_transactions: int
    completed_transactions: int
    partially_completed_transactions: int
    rejected_transactions: int
    transaction_lines: int
    completed_lines: int
    rejected_lines: int
    completed_units: int
    rejected_units: int
    gross_sales_amount: Decimal
    discount_amount: Decimal
    net_sales_amount: Decimal
    lost_sales_amount: Decimal
    inventory_movements: int
    units_removed_from_inventory: int
    reorder_signals: int
    out_of_stock_signals: int
    replenishments_scheduled: int
    replenishments_completed: int
    units_replenished: int
