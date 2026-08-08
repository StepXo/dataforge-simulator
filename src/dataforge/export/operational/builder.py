"""Incremental mapping from simulation state to operational records."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from dataforge.core.state.simulation_state import SimulationState, require_tick_context
from dataforge.engines.inventory.models import InventoryContext, InventoryMovement
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
)
from dataforge.engines.transaction.models import Transaction, TransactionContext
from dataforge.engines.validation.models import ValidationContext
from dataforge.export.operational.sink import OperationalRecord
from dataforge.generators.customers.models import Customer
from dataforge.generators.geography.models import (
    AdministrativeArea,
    City,
    Country,
    Location,
    Region,
)
from dataforge.generators.inventory.models import InventoryItem
from dataforge.generators.products.models import Category, Product
from dataforge.generators.promotions.models import Promotion

if TYPE_CHECKING:
    from dataforge.runtime.result import SimulationResult


class OperationalDataBuilder:
    """Map master, one validated tick, and final state without large buffers."""

    def iter_master_rows(self, state: SimulationState) -> Iterator[OperationalRecord]:
        """Yield bootstrap/master rows once after bootstrap."""
        for country in self._values(state, "countries", Country):
            yield OperationalRecord(
                "countries",
                {"country_id": country.id, "code": country.code, "name": country.name},
            )
        for region in self._values(state, "regions", Region):
            yield OperationalRecord(
                "regions",
                {
                    "region_id": region.id,
                    "name": region.name,
                    "country_id": region.country_id,
                },
            )
        for area in self._values(state, "administrative_areas", AdministrativeArea):
            yield OperationalRecord(
                "administrative_areas",
                {
                    "administrative_area_id": area.id,
                    "name": area.name,
                    "area_type": area.area_type,
                    "region_id": area.region_id,
                    "country_id": area.country_id,
                },
            )
        for city in self._values(state, "cities", City):
            yield OperationalRecord(
                "cities",
                {
                    "city_id": city.id,
                    "name": city.name,
                    "administrative_area_id": city.administrative_area_id,
                    "region_id": city.region_id,
                    "country_id": city.country_id,
                },
            )
        for location in self._values(state, "locations", Location):
            yield OperationalRecord(
                "locations",
                {
                    "location_id": location.id,
                    "name": location.name,
                    "city_id": location.city_id,
                    "administrative_area_id": location.administrative_area_id,
                    "region_id": location.region_id,
                    "country_id": location.country_id,
                    "capacity": location.capacity,
                    "activity_factor": location.activity_factor,
                    "opened_at": location.opened_at,
                },
            )
        for category in self._values(state, "categories", Category):
            yield OperationalRecord(
                "categories", {"category_id": category.id, "name": category.name}
            )
        for product in self._values(state, "products", Product):
            yield OperationalRecord(
                "products",
                {
                    "product_id": product.id,
                    "name": product.name,
                    "category_id": product.category_id,
                    "currency": product.currency,
                    "base_price": product.base_price,
                    "base_cost": product.base_cost,
                    "base_margin": product.base_margin,
                    "activity_factor": product.activity_factor,
                    "active": product.active,
                },
            )
        for customer in self._values(state, "customers", Customer):
            yield OperationalRecord(
                "customers",
                {
                    "customer_id": customer.id,
                    "home_city_id": customer.home_city_id,
                    "home_region_id": customer.home_region_id,
                    "preferred_location_id": customer.preferred_location_id,
                    "segment": customer.segment.value,
                    "purchase_frequency": customer.purchase_frequency,
                    "preferred_channel": customer.preferred_channel.value,
                    "promotion_sensitivity": customer.promotion_sensitivity,
                    "activity_factor": customer.activity_factor,
                    "registered_at": customer.registered_at,
                    "active": customer.active,
                },
            )
        for promotion in self._values(state, "promotions", Promotion):
            yield OperationalRecord(
                "promotions",
                {
                    "promotion_id": promotion.id,
                    "name": promotion.name,
                    "start_date": promotion.start_date,
                    "end_date": promotion.end_date,
                    "target_type": promotion.target_type.value,
                    "channel": promotion.channel.value,
                    "discount_rate": promotion.discount_rate,
                    "demand_lift": promotion.demand_lift,
                    "active": promotion.active,
                },
            )
            for target_id in promotion.target_ids:
                yield OperationalRecord(
                    "promotion_targets",
                    {"promotion_id": promotion.id, "target_id": target_id},
                )

    def iter_tick_rows(
        self, state: SimulationState, tick_index: int
    ) -> Iterator[OperationalRecord]:
        """Yield historical facts for exactly one validated tick."""
        validation = require_tick_context(
            state,
            "validation_context",
            tick_index,
            ValidationContext,
            owner="operational output",
        )
        if not validation.valid:
            raise ValueError(f"Tick is not valid for operational output: {tick_index}")
        transactions = require_tick_context(
            state,
            "transaction_context",
            tick_index,
            TransactionContext,
            owner="operational output",
        )
        for transaction in transactions.transactions:
            yield from self._transaction_rows(transaction)

        inventory = require_tick_context(
            state,
            "inventory_context",
            tick_index,
            InventoryContext,
            owner="operational output",
        )
        for movement in inventory.movements:
            yield self._movement_row(movement)
        replenishment = require_tick_context(
            state,
            "replenishment_context",
            tick_index,
            ReplenishmentContext,
            owner="operational output",
        )
        for movement in replenishment.movements:
            yield self._movement_row(movement)

        metrics = require_tick_context(
            state,
            "metrics_context",
            tick_index,
            MetricsContext,
            owner="operational output",
        )
        yield OperationalRecord(
            "metrics",
            {name: getattr(metrics, name) for name in metrics.__dataclass_fields__},
        )

    def iter_final_rows(self, state: SimulationState) -> Iterator[OperationalRecord]:
        """Yield final snapshots after all ticks complete."""
        for inventory_item in self._values(state, "inventory", InventoryItem):
            yield OperationalRecord(
                "inventory",
                {
                    "inventory_id": inventory_item.id,
                    "location_id": inventory_item.location_id,
                    "product_id": inventory_item.product_id,
                    "current_stock": inventory_item.current_stock,
                    "reorder_point": inventory_item.reorder_point,
                    "max_stock": inventory_item.max_stock,
                    "active": inventory_item.active,
                },
            )
        if state.has_collection("pending_replenishments"):
            for replenishment_item in self._values(
                state, "pending_replenishments", PendingReplenishment
            ):
                yield OperationalRecord(
                    "replenishments",
                    {
                        "replenishment_id": replenishment_item.id,
                        "inventory_id": replenishment_item.inventory_id,
                        "location_id": replenishment_item.location_id,
                        "product_id": replenishment_item.product_id,
                        "requested_quantity": replenishment_item.requested_quantity,
                        "requested_tick_index": replenishment_item.requested_tick_index,
                        "due_tick_index": replenishment_item.due_tick_index,
                        "created_at": replenishment_item.created_at,
                        "status": replenishment_item.status.value,
                    },
                )

    def iter_result_rows(self, result: SimulationResult) -> Iterator[OperationalRecord]:
        """Yield the same logical records from a retained full-history result."""
        yield from self.iter_master_rows(result.state)
        for tick_index in range(result.simulation_summary.ticks_processed):
            yield from self.iter_tick_rows(result.state, tick_index)
        yield from self.iter_final_rows(result.state)

    def _transaction_rows(
        self, transaction: Transaction
    ) -> Iterator[OperationalRecord]:
        yield OperationalRecord(
            "transactions",
            {
                "transaction_id": transaction.id,
                "basket_id": transaction.basket_id,
                "customer_id": transaction.customer_id,
                "location_id": transaction.location_id,
                "channel": transaction.channel.value,
                "currency": transaction.currency,
                "gross_amount": transaction.gross_amount,
                "discount_amount": transaction.discount_amount,
                "net_amount": transaction.net_amount,
                "lost_sales_amount": transaction.lost_sales_amount,
                "completed_units": transaction.completed_units,
                "rejected_units": transaction.rejected_units,
                "status": transaction.status.value,
                "tick_index": transaction.tick_index,
                "occurred_at": transaction.occurred_at,
            },
        )
        for line in transaction.lines:
            yield OperationalRecord(
                "transaction_lines",
                {
                    "transaction_line_id": line.id,
                    "transaction_id": transaction.id,
                    "intent_id": line.intent_id,
                    "quote_intent_id": line.quote_intent_id,
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "gross_amount": line.gross_amount,
                    "discount_amount": line.discount_amount,
                    "net_amount": line.net_amount,
                    "status": line.status.value,
                    "rejection_reason": (
                        line.rejection_reason.value if line.rejection_reason else None
                    ),
                },
            )
            for promotion_id in line.applied_promotion_ids:
                yield OperationalRecord(
                    "transaction_line_promotions",
                    {
                        "transaction_line_id": line.id,
                        "promotion_id": promotion_id,
                    },
                )

    @staticmethod
    def _movement_row(movement: InventoryMovement) -> OperationalRecord:
        return OperationalRecord(
            "inventory_movements",
            {
                "movement_id": movement.id,
                "inventory_id": movement.inventory_id,
                "location_id": movement.location_id,
                "product_id": movement.product_id,
                "transaction_id": movement.transaction_id,
                "basket_id": movement.basket_id,
                "movement_type": movement.movement_type.value,
                "quantity": movement.quantity,
                "stock_before": movement.stock_before,
                "stock_after": movement.stock_after,
                "tick_index": movement.tick_index,
                "occurred_at": movement.occurred_at,
            },
        )

    @staticmethod
    def _values[T](
        state: SimulationState, collection_name: str, expected_type: type[T]
    ) -> tuple[T, ...]:
        if not state.has_collection(collection_name):
            raise ValueError(
                f"Required operational collection is missing: {collection_name}"
            )
        values = state.collection(collection_name).all()
        typed = tuple(value for value in values if isinstance(value, expected_type))
        if len(typed) != len(values):
            raise ValueError(
                f"Operational collection contains invalid records: {collection_name}"
            )
        return typed
