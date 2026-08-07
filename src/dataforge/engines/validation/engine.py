"""Fail-fast validation of master state and per-tick engine outputs."""

from collections import Counter

from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.engines.customer_behavior.models import CustomerBehaviorContext
from dataforge.engines.demand.models import DemandContext
from dataforge.engines.inventory.models import InventoryContext, InventoryMovementType
from dataforge.engines.metrics.models import MetricsContext
from dataforge.engines.pricing.models import PricingContext
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
    ReplenishmentStatus,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.engines.transaction.models import (
    TransactionContext,
    TransactionLineStatus,
    TransactionStatus,
)
from dataforge.engines.validation.events import StateValidationCompleted
from dataforge.engines.validation.models import ValidationContext
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

VALIDATION_CONTEXT_COLLECTION = "validation_context"


class StateValidationEngine:
    """Detect inconsistent state without repairing or mutating business data."""

    def execute(self, context: SimulationContext, clock: SimulationClock) -> None:
        key = f"tick-{clock.tick_index}"
        if context.state.has_collection(VALIDATION_CONTEXT_COLLECTION):
            output = context.state.collection(VALIDATION_CONTEXT_COLLECTION)
            if output.contains(key):
                raise ValueError(f"StateValidationEngine already executed for {key}")
        else:
            output = context.state.create_collection(VALIDATION_CONTEXT_COLLECTION)

        checked: set[str] = set()
        checks = 0
        master = self._master(context, checked)
        self._validate_geography(master)
        checks += 1
        self._validate_products(master)
        checks += 1
        self._validate_customers(master)
        checks += 1
        assortment = self._validate_inventory(master)
        checks += 1
        self._validate_pending(master)
        checks += 1

        temporal = self._tick(
            context, checked, "temporal_context", key, TemporalContext
        )
        if (
            temporal.tick_index != clock.tick_index
            or temporal.current_time != clock.current_time
        ):
            raise ValueError("TemporalContext does not match SimulationClock")
        checks += 1
        demand = self._tick(context, checked, "demand_context", key, DemandContext)
        self._validate_demand(demand, master, assortment)
        checks += 1
        behavior = self._tick(
            context, checked, "customer_behavior_context", key, CustomerBehaviorContext
        )
        self._validate_behavior(
            behavior, temporal, master, assortment, clock.tick_index
        )
        checks += 1
        pricing = self._tick(context, checked, "pricing_context", key, PricingContext)
        self._validate_pricing(pricing, behavior)
        checks += 1
        transactions = self._tick(
            context, checked, "transaction_context", key, TransactionContext
        )
        self._validate_transactions(transactions, behavior, pricing)
        checks += 1
        inventory_context = self._tick(
            context, checked, "inventory_context", key, InventoryContext
        )
        self._validate_inventory_context(inventory_context, transactions)
        checks += 1
        replenishment = self._tick(
            context, checked, "replenishment_context", key, ReplenishmentContext
        )
        self._validate_replenishment_context(replenishment, master)
        checks += 1
        metrics = self._tick(context, checked, "metrics_context", key, MetricsContext)
        self._validate_metrics(
            metrics,
            demand,
            behavior,
            pricing,
            transactions,
            inventory_context,
            replenishment,
        )
        checks += 1

        result = ValidationContext(
            clock.tick_index, temporal.current_time, checks, len(checked), True
        )
        output.add(key, result)
        context.event_bus.publish(StateValidationCompleted(result))

    def _master(
        self, context: SimulationContext, checked: set[str]
    ) -> dict[str, tuple[object, ...]]:
        names = (
            "countries",
            "regions",
            "administrative_areas",
            "cities",
            "locations",
            "categories",
            "products",
            "customers",
            "inventory",
            "pending_replenishments",
        )
        return {name: self._collection(context, checked, name) for name in names}

    def _validate_geography(self, data: dict[str, tuple[object, ...]]) -> None:
        countries = self._index(data["countries"], Country, "countries")
        regions = self._index(data["regions"], Region, "regions")
        areas = self._index(
            data["administrative_areas"], AdministrativeArea, "administrative_areas"
        )
        cities = self._index(data["cities"], City, "cities")
        for region in regions.values():
            if region.country_id not in countries:
                raise ValueError(f"Region '{region.id}' references missing country")
        for area in areas.values():
            region_ref = regions.get(area.region_id)
            if (
                region_ref is None
                or area.country_id not in countries
                or region_ref.country_id != area.country_id
            ):
                raise ValueError(
                    f"Administrative area '{area.id}' has inconsistent geography"
                )
        for city in cities.values():
            area_ref = areas.get(city.administrative_area_id)
            region_ref = regions.get(city.region_id)
            if area_ref is None:
                raise ValueError(
                    f"City '{city.id}' references missing administrative area"
                )
            if (
                region_ref is None
                or city.country_id not in countries
                or (area_ref.region_id, area_ref.country_id)
                != (city.region_id, city.country_id)
            ):
                raise ValueError(f"City '{city.id}' has inconsistent geography")
        for location in self._typed(data["locations"], Location, "locations"):
            city_ref = cities.get(location.city_id)
            area_ref = areas.get(location.administrative_area_id)
            region_ref = regions.get(location.region_id)
            if (
                city_ref is None
                or area_ref is None
                or region_ref is None
                or location.country_id not in countries
            ):
                raise ValueError(
                    f"Location '{location.id}' references missing geography"
                )
            chain = (
                location.administrative_area_id,
                location.region_id,
                location.country_id,
            )
            if chain != (
                city_ref.administrative_area_id,
                city_ref.region_id,
                city_ref.country_id,
            ) or (area_ref.region_id, area_ref.country_id) != (
                location.region_id,
                location.country_id,
            ):
                raise ValueError(f"Location '{location.id}' has inconsistent geography")

    def _validate_products(self, data: dict[str, tuple[object, ...]]) -> None:
        categories = self._index(data["categories"], Category, "categories")
        for product in self._typed(data["products"], Product, "products"):
            if product.category_id not in categories:
                raise ValueError(f"Product '{product.id}' references missing category")

    def _validate_customers(self, data: dict[str, tuple[object, ...]]) -> None:
        cities = self._index(data["cities"], City, "cities")
        regions = self._index(data["regions"], Region, "regions")
        locations = self._index(data["locations"], Location, "locations")
        for customer in self._typed(data["customers"], Customer, "customers"):
            city = cities.get(customer.home_city_id)
            location = locations.get(customer.preferred_location_id)
            if (
                city is None
                or customer.home_region_id not in regions
                or location is None
            ):
                raise ValueError(
                    f"Customer '{customer.id}' references missing geography"
                )
            if (
                city.region_id != customer.home_region_id
                or location.region_id != customer.home_region_id
            ):
                raise ValueError(f"Customer '{customer.id}' has inconsistent geography")

    def _validate_inventory(
        self, data: dict[str, tuple[object, ...]]
    ) -> dict[tuple[str, str], InventoryItem]:
        locations = self._index(data["locations"], Location, "locations")
        products = self._index(data["products"], Product, "products")
        assortment: dict[tuple[str, str], InventoryItem] = {}
        for item in self._typed(data["inventory"], InventoryItem, "inventory"):
            if item.location_id not in locations or item.product_id not in products:
                raise ValueError(
                    f"Inventory item '{item.id}' references missing master data"
                )
            if item.current_stock < 0:
                raise ValueError(f"Inventory item '{item.id}' has negative stock")
            if (
                min(item.reorder_point, item.max_stock) < 0
                or item.reorder_point > item.max_stock
                or item.current_stock > item.max_stock
            ):
                raise ValueError(f"Inventory item '{item.id}' has invalid stock limits")
            key = (item.location_id, item.product_id)
            if key in assortment:
                raise ValueError(f"Duplicate inventory assortment for '{item.id}'")
            assortment[key] = item
        return assortment

    def _validate_pending(self, data: dict[str, tuple[object, ...]]) -> None:
        inventory = self._index(data["inventory"], InventoryItem, "inventory")
        pending_ids: set[str] = set()
        for item in self._typed(
            data["pending_replenishments"],
            PendingReplenishment,
            "pending_replenishments",
        ):
            stock = inventory.get(item.inventory_id)
            if stock is None or (stock.location_id, stock.product_id) != (
                item.location_id,
                item.product_id,
            ):
                raise ValueError(
                    f"Replenishment '{item.id}' references inconsistent inventory"
                )
            if (
                item.requested_quantity <= 0
                or item.due_tick_index < item.requested_tick_index
            ):
                raise ValueError(
                    f"Replenishment '{item.id}' has invalid scheduling values"
                )
            if item.status is ReplenishmentStatus.PENDING:
                if item.inventory_id in pending_ids:
                    raise ValueError(
                        f"Multiple pending replenishments for '{item.inventory_id}'"
                    )
                pending_ids.add(item.inventory_id)

    def _validate_demand(
        self,
        demand: DemandContext,
        data: dict[str, tuple[object, ...]],
        assortment: dict[tuple[str, str], InventoryItem],
    ) -> None:
        locations = self._index(data["locations"], Location, "locations")
        products = self._index(data["products"], Product, "products")
        for record in demand.demands:
            stock = assortment.get((record.location_id, record.product_id))
            if (
                record.location_id not in locations
                or record.product_id not in products
                or stock is None
                or not stock.active
            ):
                raise ValueError(
                    f"Demand references unavailable assortment: {record.location_id}"
                )
            if record.expected_demand < 0 or record.requested_units < 0:
                raise ValueError("Demand contains negative values")
        if demand.total_requested_units != sum(
            item.requested_units for item in demand.demands
        ):
            raise ValueError("Demand totals are inconsistent")

    def _validate_behavior(
        self,
        behavior: CustomerBehaviorContext,
        temporal: TemporalContext,
        data: dict[str, tuple[object, ...]],
        assortment: dict[tuple[str, str], InventoryItem],
        tick: int,
    ) -> None:
        customers = self._index(data["customers"], Customer, "customers")
        locations = self._index(data["locations"], Location, "locations")
        products = self._index(data["products"], Product, "products")
        baskets: dict[str, tuple[str, str, object, int]] = {}
        for intent in behavior.intents:
            customer = customers.get(intent.customer_id)
            location = locations.get(intent.location_id)
            stock = assortment.get((intent.location_id, intent.product_id))
            if (
                customer is None
                or location is None
                or intent.product_id not in products
                or stock is None
                or not stock.active
            ):
                raise ValueError(
                    f"PurchaseIntent '{intent.id}' references invalid business data"
                )
            if (
                location.opened_at > temporal.current_time.date()
                or location.city_id != customer.home_city_id
                or location.region_id != customer.home_region_id
            ):
                raise ValueError(
                    f"PurchaseIntent '{intent.id}' violates same-city fulfillment"
                )
            if intent.requested_quantity < 1 or intent.demand_tick_index != tick:
                raise ValueError(
                    f"PurchaseIntent '{intent.id}' has invalid quantity or tick"
                )
            identity = (intent.customer_id, intent.location_id, intent.channel, tick)
            if intent.basket_id in baskets and baskets[intent.basket_id] != identity:
                raise ValueError(
                    f"Basket '{intent.basket_id}' contains inconsistent intents"
                )
            baskets[intent.basket_id] = identity

    def _validate_pricing(
        self, pricing: PricingContext, behavior: CustomerBehaviorContext
    ) -> None:
        intents = {item.id: item for item in behavior.intents}
        if len(pricing.quotes) != len(intents):
            raise ValueError("Pricing quote count does not match purchase intents")
        seen: set[str] = set()
        for quote in pricing.quotes:
            intent = intents.get(quote.intent_id)
            if quote.intent_id in seen or intent is None:
                raise ValueError(f"Invalid or duplicate PriceQuote: {quote.intent_id}")
            seen.add(quote.intent_id)
            identity = (
                quote.basket_id,
                quote.customer_id,
                quote.location_id,
                quote.product_id,
                quote.channel,
                quote.quantity,
            )
            expected_identity = (
                intent.basket_id,
                intent.customer_id,
                intent.location_id,
                intent.product_id,
                intent.channel,
                intent.requested_quantity,
            )
            if identity != expected_identity:
                raise ValueError(f"PriceQuote does not match intent: {quote.intent_id}")
            amounts = (
                quote.unit_base_price,
                quote.unit_discount_amount,
                quote.unit_effective_price,
                quote.gross_amount,
                quote.discount_amount,
                quote.net_amount,
            )
            if (
                any(value < 0 for value in amounts)
                or quote.unit_base_price - quote.unit_discount_amount
                != quote.unit_effective_price
                or quote.gross_amount - quote.discount_amount != quote.net_amount
            ):
                raise ValueError(
                    f"PriceQuote monetary values are inconsistent: {quote.intent_id}"
                )

    def _validate_transactions(
        self,
        transactions: TransactionContext,
        behavior: CustomerBehaviorContext,
        pricing: PricingContext,
    ) -> None:
        intents = {item.id: item for item in behavior.intents}
        quotes = {item.intent_id: item for item in pricing.quotes}
        expected_baskets = {item.basket_id for item in behavior.intents}
        actual_baskets = [item.basket_id for item in transactions.transactions]
        if (
            len(actual_baskets) != len(set(actual_baskets))
            or set(actual_baskets) != expected_baskets
        ):
            raise ValueError("Transactions must contain exactly one basket aggregate")
        for transaction in transactions.transactions:
            completed = 0
            rejected = 0
            for line in transaction.lines:
                intent = intents.get(line.intent_id)
                quote = quotes.get(line.quote_intent_id)
                if intent is None or quote is None:
                    raise ValueError(
                        f"TransactionLine '{line.id}' references missing "
                        "intent or quote"
                    )
                identity = (
                    transaction.basket_id,
                    transaction.customer_id,
                    transaction.location_id,
                    line.product_id,
                    transaction.channel,
                    line.quantity,
                )
                expected_identity = (
                    intent.basket_id,
                    intent.customer_id,
                    intent.location_id,
                    intent.product_id,
                    intent.channel,
                    intent.requested_quantity,
                )
                money = (
                    line.unit_price,
                    line.gross_amount,
                    line.discount_amount,
                    line.net_amount,
                    line.applied_promotion_ids,
                )
                quote_money = (
                    quote.unit_effective_price,
                    quote.gross_amount,
                    quote.discount_amount,
                    quote.net_amount,
                    quote.applied_promotion_ids,
                )
                if identity != expected_identity or money != quote_money:
                    raise ValueError(
                        f"TransactionLine '{line.id}' is inconsistent with pricing"
                    )
                if line.status is TransactionLineStatus.COMPLETED:
                    completed += 1
                else:
                    rejected += 1
            expected_status = (
                TransactionStatus.COMPLETED
                if not rejected
                else TransactionStatus.REJECTED
                if not completed
                else TransactionStatus.PARTIALLY_COMPLETED
            )
            if transaction.status is not expected_status:
                raise ValueError(
                    f"Transaction '{transaction.id}' has inconsistent status"
                )

    def _validate_inventory_context(
        self, inventory: InventoryContext, transactions: TransactionContext
    ) -> None:
        expected = Counter(
            (transaction.id, transaction.location_id, line.product_id, line.quantity)
            for transaction in transactions.transactions
            for line in transaction.lines
            if line.status is TransactionLineStatus.COMPLETED
        )
        actual: Counter[tuple[str, str, str, int]] = Counter()
        for movement in inventory.movements:
            if movement.movement_type is not InventoryMovementType.SALE:
                raise ValueError("InventoryContext contains non-sale movement")
            if movement.transaction_id is None:
                raise ValueError("Sale movement requires transaction ID")
            actual[
                (
                    movement.transaction_id,
                    movement.location_id,
                    movement.product_id,
                    movement.quantity,
                )
            ] += 1
            if (
                movement.stock_before - movement.quantity != movement.stock_after
                or min(movement.stock_before, movement.stock_after) < 0
            ):
                raise ValueError(f"Inventory movement '{movement.id}' is inconsistent")
        if (
            actual != expected
            or inventory.total_units_sold != transactions.completed_units
        ):
            raise ValueError(
                "Completed transaction lines and sale movements do not match"
            )
        changed = {(x.location_id, x.product_id) for x in inventory.movements}
        if inventory.inventory_items_changed != len(changed):
            raise ValueError("Inventory items changed count is inconsistent")

    def _validate_replenishment_context(
        self, context: ReplenishmentContext, data: dict[str, tuple[object, ...]]
    ) -> None:
        inventory = self._index(data["inventory"], InventoryItem, "inventory")
        if (
            context.replenishments_scheduled != len(context.scheduled)
            or context.replenishments_completed != len(context.completed)
            or context.units_received != sum(x.quantity for x in context.movements)
        ):
            raise ValueError("ReplenishmentContext totals are inconsistent")
        for item in context.completed:
            if (
                item.status is not ReplenishmentStatus.COMPLETED
                or item.inventory_id not in inventory
            ):
                raise ValueError(f"Completed replenishment '{item.id}' is invalid")
        for movement in context.movements:
            if (
                movement.movement_type is not InventoryMovementType.REPLENISHMENT
                or movement.stock_after - movement.stock_before != movement.quantity
            ):
                raise ValueError(
                    f"Replenishment movement '{movement.id}' is inconsistent"
                )

    def _validate_metrics(
        self,
        metrics: MetricsContext,
        demand: DemandContext,
        behavior: CustomerBehaviorContext,
        pricing: PricingContext,
        transactions: TransactionContext,
        inventory: InventoryContext,
        replenishment: ReplenishmentContext,
    ) -> None:
        expected = (
            len(demand.demands),
            demand.total_requested_units,
            behavior.total_intents,
            behavior.total_requested_units,
            behavior.unassigned_demand_units,
            len(pricing.quotes),
            transactions.total_transactions,
            transactions.completed_transactions,
            transactions.partially_completed_transactions,
            transactions.rejected_transactions,
            transactions.transaction_lines,
            transactions.completed_lines,
            transactions.rejected_lines,
            transactions.completed_units,
            transactions.rejected_units,
            transactions.gross_amount,
            transactions.discount_amount,
            transactions.net_amount,
            transactions.lost_sales_amount,
            len(inventory.movements),
            inventory.total_units_sold,
            len(inventory.reorder_signals),
            len(inventory.out_of_stock_signals),
            replenishment.replenishments_scheduled,
            replenishment.replenishments_completed,
            replenishment.units_received,
        )
        actual = (
            metrics.demand_records,
            metrics.demand_units,
            metrics.purchase_intents,
            metrics.intent_units,
            metrics.unassigned_demand_units,
            metrics.price_quotes,
            metrics.total_transactions,
            metrics.completed_transactions,
            metrics.partially_completed_transactions,
            metrics.rejected_transactions,
            metrics.transaction_lines,
            metrics.completed_lines,
            metrics.rejected_lines,
            metrics.completed_units,
            metrics.rejected_units,
            metrics.gross_sales_amount,
            metrics.discount_amount,
            metrics.net_sales_amount,
            metrics.lost_sales_amount,
            metrics.inventory_movements,
            metrics.units_removed_from_inventory,
            metrics.reorder_signals,
            metrics.out_of_stock_signals,
            metrics.replenishments_scheduled,
            metrics.replenishments_completed,
            metrics.units_replenished,
        )
        if actual != expected:
            raise ValueError("MetricsContext does not match source contexts")
        if (
            behavior.total_requested_units + behavior.unassigned_demand_units
            != demand.total_requested_units
            or transactions.completed_units + transactions.rejected_units
            != behavior.total_requested_units
        ):
            raise ValueError("Demand or transaction conservation is inconsistent")

    def _collection(
        self, context: SimulationContext, checked: set[str], name: str
    ) -> tuple[object, ...]:
        if not context.state.has_collection(name):
            raise ValueError(f"Required validation collection is missing: {name}")
        checked.add(name)
        return context.state.collection(name).all()

    def _tick[T](
        self,
        context: SimulationContext,
        checked: set[str],
        name: str,
        key: str,
        expected_type: type[T],
    ) -> T:
        self._collection(context, checked, name)
        value = context.state.collection(name).get(key)
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} context is missing for {key}")
        return value

    def _typed[T](
        self, values: tuple[object, ...], expected_type: type[T], name: str
    ) -> tuple[T, ...]:
        typed = tuple(item for item in values if isinstance(item, expected_type))
        if len(typed) != len(values):
            raise ValueError(f"Collection '{name}' contains invalid records")
        return typed

    def _index[T](
        self, values: tuple[object, ...], expected_type: type[T], name: str
    ) -> dict[str, T]:
        result: dict[str, T] = {}
        for item in self._typed(values, expected_type, name):
            identifier = getattr(item, "id", None)
            if not isinstance(identifier, str) or identifier in result:
                raise ValueError(
                    f"Collection '{name}' contains invalid or duplicate IDs"
                )
            result[identifier] = item
        return result
