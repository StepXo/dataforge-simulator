"""Single source of truth for DataForge operational dataset schemas."""

from dataforge.export.operational.model import (
    ColumnDefinition,
    DatasetDefinition,
    LogicalDataType,
    OperationalDataModel,
    RelationshipDefinition,
)


def build_operational_data_model() -> OperationalDataModel:
    """Build the format-independent operational data model."""
    column = ColumnDefinition
    dataset = DatasetDefinition
    relationship = RelationshipDefinition
    string = LogicalDataType.STRING
    integer = LogicalDataType.INTEGER
    decimal = LogicalDataType.DECIMAL
    floating = LogicalDataType.FLOAT
    boolean = LogicalDataType.BOOLEAN
    date = LogicalDataType.DATE
    datetime = LogicalDataType.DATETIME

    return OperationalDataModel(
        datasets=(
            dataset(
                name="countries",
                columns=(
                    column("country_id", string),
                    column("code", string),
                    column("name", string),
                ),
                primary_key=("country_id",),
            ),
            dataset(
                name="regions",
                columns=(
                    column("region_id", string),
                    column("name", string),
                    column("country_id", string),
                ),
                primary_key=("region_id",),
                relationships=(relationship("country_id", "countries", "country_id"),),
            ),
            dataset(
                name="administrative_areas",
                columns=(
                    column("administrative_area_id", string),
                    column("name", string),
                    column("area_type", string),
                    column("region_id", string),
                    column("country_id", string),
                ),
                primary_key=("administrative_area_id",),
                relationships=(
                    relationship("region_id", "regions", "region_id"),
                    relationship("country_id", "countries", "country_id"),
                ),
            ),
            dataset(
                name="cities",
                columns=(
                    column("city_id", string),
                    column("name", string),
                    column("administrative_area_id", string),
                    column("region_id", string),
                    column("country_id", string),
                ),
                primary_key=("city_id",),
                relationships=(
                    relationship(
                        "administrative_area_id",
                        "administrative_areas",
                        "administrative_area_id",
                    ),
                    relationship("region_id", "regions", "region_id"),
                    relationship("country_id", "countries", "country_id"),
                ),
            ),
            dataset(
                name="locations",
                columns=(
                    column("location_id", string),
                    column("name", string),
                    column("city_id", string),
                    column("administrative_area_id", string),
                    column("region_id", string),
                    column("country_id", string),
                    column("capacity", integer),
                    column("activity_factor", floating),
                    column("opened_at", date),
                ),
                primary_key=("location_id",),
                relationships=(
                    relationship("city_id", "cities", "city_id"),
                    relationship(
                        "administrative_area_id",
                        "administrative_areas",
                        "administrative_area_id",
                    ),
                    relationship("region_id", "regions", "region_id"),
                    relationship("country_id", "countries", "country_id"),
                ),
            ),
            dataset(
                name="categories",
                columns=(
                    column("category_id", string),
                    column("name", string),
                ),
                primary_key=("category_id",),
            ),
            dataset(
                name="products",
                columns=(
                    column("product_id", string),
                    column("name", string),
                    column("category_id", string),
                    column("currency", string),
                    column("base_price", decimal),
                    column("base_cost", decimal),
                    column("base_margin", decimal),
                    column("activity_factor", floating),
                    column("active", boolean),
                ),
                primary_key=("product_id",),
                relationships=(
                    relationship("category_id", "categories", "category_id"),
                ),
            ),
            dataset(
                name="customers",
                columns=(
                    column("customer_id", string),
                    column("home_city_id", string),
                    column("home_region_id", string),
                    column("preferred_location_id", string),
                    column("segment", string),
                    column("purchase_frequency", floating),
                    column("preferred_channel", string),
                    column("promotion_sensitivity", floating),
                    column("activity_factor", floating),
                    column("registered_at", date),
                    column("active", boolean),
                ),
                primary_key=("customer_id",),
                relationships=(
                    relationship("home_city_id", "cities", "city_id"),
                    relationship("home_region_id", "regions", "region_id"),
                    relationship("preferred_location_id", "locations", "location_id"),
                ),
            ),
            dataset(
                name="promotions",
                columns=(
                    column("promotion_id", string),
                    column("name", string),
                    column("start_date", date),
                    column("end_date", date),
                    column("target_type", string),
                    column("channel", string),
                    column("discount_rate", floating),
                    column("demand_lift", floating),
                    column("active", boolean),
                ),
                primary_key=("promotion_id",),
            ),
            dataset(
                name="promotion_targets",
                columns=(
                    column("promotion_id", string),
                    column("target_id", string),
                ),
                primary_key=("promotion_id", "target_id"),
                relationships=(
                    relationship("promotion_id", "promotions", "promotion_id"),
                ),
            ),
            dataset(
                name="transactions",
                columns=(
                    column("transaction_id", string),
                    column("basket_id", string),
                    column("customer_id", string),
                    column("location_id", string),
                    column("channel", string),
                    column("currency", string),
                    column("gross_amount", decimal),
                    column("discount_amount", decimal),
                    column("net_amount", decimal),
                    column("lost_sales_amount", decimal),
                    column("completed_units", integer),
                    column("rejected_units", integer),
                    column("status", string),
                    column("tick_index", integer),
                    column("occurred_at", datetime),
                ),
                primary_key=("transaction_id",),
                relationships=(
                    relationship("customer_id", "customers", "customer_id"),
                    relationship("location_id", "locations", "location_id"),
                ),
            ),
            dataset(
                name="transaction_lines",
                columns=(
                    column("transaction_line_id", string),
                    column("transaction_id", string),
                    column("intent_id", string),
                    column("quote_intent_id", string),
                    column("product_id", string),
                    column("quantity", integer),
                    column("unit_price", decimal),
                    column("gross_amount", decimal),
                    column("discount_amount", decimal),
                    column("net_amount", decimal),
                    column("status", string),
                    column("rejection_reason", string, nullable=True),
                ),
                primary_key=("transaction_line_id",),
                relationships=(
                    relationship("transaction_id", "transactions", "transaction_id"),
                    relationship("product_id", "products", "product_id"),
                ),
            ),
            dataset(
                name="transaction_line_promotions",
                columns=(
                    column("transaction_line_id", string),
                    column("promotion_id", string),
                ),
                primary_key=("transaction_line_id", "promotion_id"),
                relationships=(
                    relationship(
                        "transaction_line_id",
                        "transaction_lines",
                        "transaction_line_id",
                    ),
                    relationship("promotion_id", "promotions", "promotion_id"),
                ),
            ),
            dataset(
                name="inventory",
                columns=(
                    column("inventory_id", string),
                    column("location_id", string),
                    column("product_id", string),
                    column("current_stock", integer),
                    column("reorder_point", integer),
                    column("max_stock", integer),
                    column("active", boolean),
                ),
                primary_key=("inventory_id",),
                relationships=(
                    relationship("location_id", "locations", "location_id"),
                    relationship("product_id", "products", "product_id"),
                ),
            ),
            dataset(
                name="inventory_movements",
                columns=(
                    column("movement_id", string),
                    column("inventory_id", string),
                    column("location_id", string),
                    column("product_id", string),
                    column("transaction_id", string, nullable=True),
                    column("basket_id", string, nullable=True),
                    column("movement_type", string),
                    column("quantity", integer),
                    column("stock_before", integer),
                    column("stock_after", integer),
                    column("tick_index", integer),
                    column("occurred_at", datetime),
                ),
                primary_key=("movement_id",),
                relationships=(
                    relationship("inventory_id", "inventory", "inventory_id"),
                    relationship("location_id", "locations", "location_id"),
                    relationship("product_id", "products", "product_id"),
                    relationship("transaction_id", "transactions", "transaction_id"),
                ),
            ),
            dataset(
                name="replenishments",
                columns=(
                    column("replenishment_id", string),
                    column("inventory_id", string),
                    column("location_id", string),
                    column("product_id", string),
                    column("requested_quantity", integer),
                    column("requested_tick_index", integer),
                    column("due_tick_index", integer),
                    column("created_at", datetime),
                    column("status", string),
                ),
                primary_key=("replenishment_id",),
                relationships=(
                    relationship("inventory_id", "inventory", "inventory_id"),
                    relationship("location_id", "locations", "location_id"),
                    relationship("product_id", "products", "product_id"),
                ),
            ),
            dataset(
                name="metrics",
                columns=(
                    column("tick_index", integer),
                    column("current_time", datetime),
                    column("demand_records", integer),
                    column("demand_units", integer),
                    column("purchase_intents", integer),
                    column("intent_units", integer),
                    column("unassigned_demand_units", integer),
                    column("price_quotes", integer),
                    column("total_transactions", integer),
                    column("completed_transactions", integer),
                    column("partially_completed_transactions", integer),
                    column("rejected_transactions", integer),
                    column("transaction_lines", integer),
                    column("completed_lines", integer),
                    column("rejected_lines", integer),
                    column("completed_units", integer),
                    column("rejected_units", integer),
                    column("gross_sales_amount", decimal),
                    column("discount_amount", decimal),
                    column("net_sales_amount", decimal),
                    column("lost_sales_amount", decimal),
                    column("inventory_movements", integer),
                    column("units_removed_from_inventory", integer),
                    column("reorder_signals", integer),
                    column("out_of_stock_signals", integer),
                    column("replenishments_scheduled", integer),
                    column("replenishments_completed", integer),
                    column("units_replenished", integer),
                ),
                primary_key=("tick_index",),
            ),
        )
    )
