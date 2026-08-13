"""Explicit dimensional schema derived from the operational model."""

from dataforge.analytics.model import (
    AnalyticalColumnDefinition,
    AnalyticalDatasetDefinition,
    AnalyticalDatasetKind,
    AnalyticalModel,
    AnalyticalRelationshipDefinition,
)
from dataforge.export.operational.model import LogicalDataType


def build_analytical_model() -> AnalyticalModel:
    column = AnalyticalColumnDefinition
    dataset = AnalyticalDatasetDefinition
    relation = AnalyticalRelationshipDefinition
    dimension = AnalyticalDatasetKind.DIMENSION
    fact = AnalyticalDatasetKind.FACT
    bridge = AnalyticalDatasetKind.BRIDGE
    string = LogicalDataType.STRING
    integer = LogicalDataType.INTEGER
    decimal = LogicalDataType.DECIMAL
    floating = LogicalDataType.FLOAT
    boolean = LogicalDataType.BOOLEAN
    date = LogicalDataType.DATE
    datetime = LogicalDataType.DATETIME

    return AnalyticalModel(
        datasets=(
            dataset(
                "dim_date",
                dimension,
                "one calendar date",
                (
                    "metrics",
                    "transactions",
                    "inventory_movements",
                    "replenishments",
                ),
                (
                    column("date", date),
                    column("year", integer),
                    column("quarter", integer),
                    column("month_number", integer),
                    column("month_name", string),
                    column("iso_week", integer),
                    column("iso_week_year", integer),
                    column("iso_weekday", integer),
                    column("weekday_name", string),
                    column("weekend", boolean),
                ),
                ("date",),
            ),
            dataset(
                "dim_customer",
                dimension,
                "one customer snapshot",
                ("customers",),
                (
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
                ("customer_id",),
            ),
            dataset(
                "dim_product",
                dimension,
                "one product snapshot",
                ("products", "categories"),
                (
                    column("product_id", string),
                    column("product_name", string),
                    column("category_id", string),
                    column("category_name", string),
                    column("currency", string),
                    column("base_price", decimal),
                    column("base_cost", decimal),
                    column("base_margin", decimal),
                    column("activity_factor", floating),
                    column("active", boolean),
                ),
                ("product_id",),
            ),
            dataset(
                "dim_location",
                dimension,
                "one location snapshot",
                ("locations", "cities", "administrative_areas", "regions", "countries"),
                (
                    column("location_id", string),
                    column("location_name", string),
                    column("city_id", string),
                    column("city_name", string),
                    column("administrative_area_id", string),
                    column("administrative_area_name", string),
                    column("administrative_area_type", string),
                    column("region_id", string),
                    column("region_name", string),
                    column("country_id", string),
                    column("country_code", string),
                    column("country_name", string),
                    column("capacity", integer),
                    column("activity_factor", floating),
                    column("opened_at", date),
                ),
                ("location_id",),
            ),
            dataset(
                "dim_promotion",
                dimension,
                "one promotion snapshot",
                ("promotions",),
                (
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
                ("promotion_id",),
            ),
            dataset(
                "fact_sales",
                fact,
                "one transaction-line outcome",
                ("transactions", "transaction_lines"),
                (
                    column("transaction_line_id", string),
                    column("transaction_id", string),
                    column("basket_id", string),
                    column("customer_id", string),
                    column("product_id", string),
                    column("location_id", string),
                    column("date", date),
                    column("occurred_at", datetime),
                    column("tick_index", integer),
                    column("channel", string),
                    column("currency", string),
                    column("transaction_status", string),
                    column("line_status", string),
                    column("rejection_reason", string, nullable=True),
                    column("quantity", integer),
                    column("unit_price", decimal),
                    column("completed_quantity", integer),
                    column("rejected_quantity", integer),
                    column("gross_sales_amount", decimal),
                    column("discount_amount", decimal),
                    column("net_sales_amount", decimal),
                    column("lost_sales_amount", decimal),
                ),
                ("transaction_line_id",),
                (
                    relation("date", "dim_date", "date"),
                    relation("customer_id", "dim_customer", "customer_id"),
                    relation("product_id", "dim_product", "product_id"),
                    relation("location_id", "dim_location", "location_id"),
                ),
            ),
            dataset(
                "fact_inventory_movement",
                fact,
                "one inventory movement",
                ("inventory_movements",),
                (
                    column("movement_id", string),
                    column("inventory_id", string),
                    column("location_id", string),
                    column("product_id", string),
                    column("transaction_id", string, nullable=True),
                    column("basket_id", string, nullable=True),
                    column("replenishment_id", string, nullable=True),
                    column("date", date),
                    column("movement_type", string),
                    column("quantity", integer),
                    column("stock_before", integer),
                    column("stock_after", integer),
                    column("tick_index", integer),
                    column("occurred_at", datetime),
                ),
                ("movement_id",),
                (
                    relation("date", "dim_date", "date"),
                    relation("product_id", "dim_product", "product_id"),
                    relation("location_id", "dim_location", "location_id"),
                    relation(
                        "replenishment_id",
                        "fact_replenishment",
                        "replenishment_id",
                    ),
                ),
            ),
            dataset(
                "fact_replenishment",
                fact,
                "one replenishment request lifecycle",
                ("replenishments",),
                (
                    column("replenishment_id", string),
                    column("inventory_id", string),
                    column("location_id", string),
                    column("product_id", string),
                    column("created_date", date),
                    column("completed_date", date, nullable=True),
                    column("requested_quantity", integer),
                    column("received_quantity", integer, nullable=True),
                    column("requested_tick_index", integer),
                    column("due_tick_index", integer),
                    column("completed_tick_index", integer, nullable=True),
                    column("created_at", datetime),
                    column("completed_at", datetime, nullable=True),
                    column("status", string),
                ),
                ("replenishment_id",),
                (
                    relation("created_date", "dim_date", "date"),
                    relation("completed_date", "dim_date", "date"),
                    relation("product_id", "dim_product", "product_id"),
                    relation("location_id", "dim_location", "location_id"),
                ),
            ),
            dataset(
                "bridge_sales_promotion",
                bridge,
                "one transaction line and applied promotion association",
                ("transaction_line_promotions",),
                (column("transaction_line_id", string), column("promotion_id", string)),
                ("transaction_line_id", "promotion_id"),
                (
                    relation(
                        "transaction_line_id", "fact_sales", "transaction_line_id"
                    ),
                    relation("promotion_id", "dim_promotion", "promotion_id"),
                ),
            ),
        )
    )
