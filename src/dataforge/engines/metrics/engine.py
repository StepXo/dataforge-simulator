"""Read-only aggregation of official per-tick engine contexts."""

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.customer_behavior.models import CustomerBehaviorContext
from dataforge.engines.demand.models import DemandContext
from dataforge.engines.inventory.models import InventoryContext
from dataforge.engines.metrics.events import MetricsContextGenerated
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.pricing.models import PricingContext
from dataforge.engines.replenishment.models import ReplenishmentContext
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import TransactionContext

METRICS_CONTEXT_COLLECTION = "metrics_context"


class MetricsEngine:
    """Create a deterministic snapshot without modifying business state."""

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        tick = clock.tick_index
        temporal = self._tick_context(
            context, "temporal_context", tick, TemporalContext
        )
        demand = self._tick_context(context, "demand_context", tick, DemandContext)
        behavior = self._tick_context(
            context, "customer_behavior_context", tick, CustomerBehaviorContext
        )
        pricing = self._tick_context(context, "pricing_context", tick, PricingContext)
        transactions = self._tick_context(
            context, "transaction_context", tick, TransactionContext
        )
        inventory = self._tick_context(
            context, "inventory_context", tick, InventoryContext
        )
        replenishment = self._tick_context(
            context, "replenishment_context", tick, ReplenishmentContext
        )
        self._validate(demand, behavior, transactions, inventory)

        result = MetricsContext(
            tick_index=tick,
            current_time=temporal.current_time,
            demand_records=len(demand.demands),
            demand_units=demand.total_requested_units,
            purchase_intents=behavior.total_intents,
            intent_units=behavior.total_requested_units,
            unassigned_demand_units=behavior.unassigned_demand_units,
            price_quotes=len(pricing.quotes),
            total_transactions=transactions.total_transactions,
            completed_transactions=transactions.completed_transactions,
            partially_completed_transactions=transactions.partially_completed_transactions,
            rejected_transactions=transactions.rejected_transactions,
            transaction_lines=transactions.transaction_lines,
            completed_lines=transactions.completed_lines,
            rejected_lines=transactions.rejected_lines,
            completed_units=transactions.completed_units,
            rejected_units=transactions.rejected_units,
            gross_sales_amount=transactions.gross_amount,
            discount_amount=transactions.discount_amount,
            net_sales_amount=transactions.net_amount,
            lost_sales_amount=transactions.lost_sales_amount,
            inventory_movements=len(inventory.movements),
            units_removed_from_inventory=inventory.total_units_sold,
            reorder_signals=len(inventory.reorder_signals),
            out_of_stock_signals=len(inventory.out_of_stock_signals),
            replenishments_scheduled=replenishment.replenishments_scheduled,
            replenishments_completed=replenishment.replenishments_completed,
            units_replenished=replenishment.units_received,
        )
        if context.state.has_collection(METRICS_CONTEXT_COLLECTION):
            collection = context.state.collection(METRICS_CONTEXT_COLLECTION)
        else:
            collection = context.state.create_collection(METRICS_CONTEXT_COLLECTION)
        collection.add(f"tick-{tick}", result)
        context.event_bus.publish(MetricsContextGenerated(result))

    def _validate(
        self,
        demand: DemandContext,
        behavior: CustomerBehaviorContext,
        transactions: TransactionContext,
        inventory: InventoryContext,
    ) -> None:
        if (
            behavior.total_requested_units + behavior.unassigned_demand_units
            != demand.total_requested_units
        ):
            raise ValueError("Intent and unassigned units must equal demand units")
        if (
            transactions.completed_units + transactions.rejected_units
            != behavior.total_requested_units
        ):
            raise ValueError("Transaction units must equal intent units")
        if inventory.total_units_sold != transactions.completed_units:
            raise ValueError("Inventory units removed must equal completed units")
        amounts = (
            transactions.gross_amount,
            transactions.discount_amount,
            transactions.net_amount,
            transactions.lost_sales_amount,
        )
        if any(amount < 0 for amount in amounts):
            raise ValueError("Transaction monetary metrics must be non-negative")
        if (
            transactions.gross_amount - transactions.discount_amount
            != transactions.net_amount
        ):
            raise ValueError("Sales monetary metrics are inconsistent")

    def _tick_context[T](
        self,
        context: SimulationContext,
        name: str,
        tick_index: int,
        expected_type: type[T],
    ) -> T:
        if not context.state.has_collection(name):
            raise ValueError(f"Required metrics collection is missing: {name}")
        value = context.state.collection(name).get(f"tick-{tick_index}")
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for tick: {tick_index}")
        return value
