"""Event published for a completed metrics snapshot."""

from dataforge.engines.metrics.models import MetricsContext
from dataforge.events.event import DomainEvent


class MetricsContextGenerated(DomainEvent):
    def __init__(self, metrics: MetricsContext) -> None:
        super().__init__(
            event_type="MetricsContextGenerated",
            payload={
                "tick_index": metrics.tick_index,
                "current_time": metrics.current_time.isoformat(),
                "demand_records": metrics.demand_records,
                "demand_units": metrics.demand_units,
                "purchase_intents": metrics.purchase_intents,
                "intent_units": metrics.intent_units,
                "unassigned_demand_units": metrics.unassigned_demand_units,
                "price_quotes": metrics.price_quotes,
                "total_transactions": metrics.total_transactions,
                "completed_transactions": metrics.completed_transactions,
                "partially_completed_transactions": (
                    metrics.partially_completed_transactions
                ),
                "rejected_transactions": metrics.rejected_transactions,
                "transaction_lines": metrics.transaction_lines,
                "completed_lines": metrics.completed_lines,
                "rejected_lines": metrics.rejected_lines,
                "completed_units": metrics.completed_units,
                "rejected_units": metrics.rejected_units,
                "gross_sales_amount": str(metrics.gross_sales_amount),
                "discount_amount": str(metrics.discount_amount),
                "net_sales_amount": str(metrics.net_sales_amount),
                "lost_sales_amount": str(metrics.lost_sales_amount),
                "inventory_movements": metrics.inventory_movements,
                "units_removed_from_inventory": metrics.units_removed_from_inventory,
                "reorder_signals": metrics.reorder_signals,
                "out_of_stock_signals": metrics.out_of_stock_signals,
                "replenishments_scheduled": metrics.replenishments_scheduled,
                "replenishments_completed": metrics.replenishments_completed,
                "units_replenished": metrics.units_replenished,
            },
        )
