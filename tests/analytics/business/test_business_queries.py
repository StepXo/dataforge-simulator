"""Focused SQL tests for supported business questions."""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest

from dataforge.analytics import AnalyticalRecord
from dataforge.analytics.business import BusinessQuery, run_business_query
from dataforge.export.analytical import DuckDBAnalyticalSink


def calendar(value: date) -> AnalyticalRecord:
    iso = value.isocalendar()
    return AnalyticalRecord(
        "dim_date",
        {
            "date": value,
            "year": value.year,
            "quarter": (value.month - 1) // 3 + 1,
            "month_number": value.month,
            "month_name": value.strftime("%B"),
            "iso_week": iso.week,
            "iso_week_year": iso.year,
            "iso_weekday": iso.weekday,
            "weekday_name": value.strftime("%A"),
            "weekend": iso.weekday >= 6,
        },
    )


def location(identifier: str, name: str) -> AnalyticalRecord:
    return AnalyticalRecord(
        "dim_location",
        {
            "location_id": identifier,
            "location_name": name,
            "city_id": "city",
            "city_name": "City",
            "administrative_area_id": "area",
            "administrative_area_name": "Area",
            "administrative_area_type": "state",
            "region_id": "region",
            "region_name": "Region",
            "country_id": "country",
            "country_code": "XX",
            "country_name": "Country",
            "capacity": 100,
            "activity_factor": 1.0,
            "opened_at": date(2020, 1, 1),
        },
    )


def product(identifier: str, name: str) -> AnalyticalRecord:
    return AnalyticalRecord(
        "dim_product",
        {
            "product_id": identifier,
            "product_name": name,
            "category_id": "category",
            "category_name": "Category",
            "currency": "USD",
            "base_price": Decimal("50.00"),
            "base_cost": Decimal("20.00"),
            "base_margin": Decimal("30.00"),
            "activity_factor": 1.0,
            "active": True,
        },
    )


def customer(identifier: str) -> AnalyticalRecord:
    return AnalyticalRecord(
        "dim_customer",
        {
            "customer_id": identifier,
            "home_city_id": "city",
            "home_region_id": "region",
            "preferred_location_id": "location-1",
            "segment": "regular",
            "purchase_frequency": 10.0,
            "preferred_channel": "physical",
            "promotion_sensitivity": 0.5,
            "activity_factor": 1.0,
            "registered_at": date(2023, 1, 1),
            "active": True,
        },
    )


def promotion(identifier: str) -> AnalyticalRecord:
    return AnalyticalRecord(
        "dim_promotion",
        {
            "promotion_id": identifier,
            "name": identifier.title(),
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 12, 31),
            "target_type": "global",
            "channel": "all",
            "discount_rate": 0.1,
            "demand_lift": 1.1,
            "active": True,
        },
    )


def sale(
    identifier: str,
    *,
    basket: str,
    customer_id: str,
    product_id: str,
    location_id: str,
    business_date: date,
    currency: str,
    channel: str,
    quantity: int,
    net: str,
    rejected: bool = False,
) -> AnalyticalRecord:
    net_amount = Decimal(net)
    return AnalyticalRecord(
        "fact_sales",
        {
            "transaction_line_id": identifier,
            "transaction_id": f"transaction-{identifier}",
            "basket_id": basket,
            "customer_id": customer_id,
            "product_id": product_id,
            "location_id": location_id,
            "date": business_date,
            "occurred_at": datetime.combine(business_date, datetime.min.time()),
            "tick_index": 0,
            "channel": channel,
            "currency": currency,
            "transaction_status": "rejected" if rejected else "completed",
            "line_status": "rejected" if rejected else "completed",
            "rejection_reason": "insufficient_stock" if rejected else None,
            "quantity": quantity,
            "unit_price": net_amount / quantity,
            "completed_quantity": 0 if rejected else quantity,
            "rejected_quantity": quantity if rejected else 0,
            "gross_sales_amount": Decimal("0.00") if rejected else net_amount,
            "discount_amount": Decimal("0.00"),
            "net_sales_amount": Decimal("0.00") if rejected else net_amount,
            "lost_sales_amount": net_amount if rejected else Decimal("0.00"),
        },
    )


def analytical_fixture() -> tuple[AnalyticalRecord, ...]:
    january = date(2024, 1, 31)
    february = date(2024, 2, 1)
    return (
        calendar(january),
        calendar(february),
        location("location-1", "North"),
        location("location-2", "South"),
        product("product-1", "First"),
        product("product-2", "Second"),
        customer("customer-1"),
        customer("customer-2"),
        promotion("promotion-1"),
        promotion("promotion-2"),
        sale(
            "line-1",
            basket="basket-1",
            customer_id="customer-1",
            product_id="product-1",
            location_id="location-1",
            business_date=january,
            currency="USD",
            channel="physical",
            quantity=2,
            net="90.00",
        ),
        sale(
            "line-2",
            basket="basket-1",
            customer_id="customer-1",
            product_id="product-2",
            location_id="location-1",
            business_date=january,
            currency="USD",
            channel="physical",
            quantity=1,
            net="50.00",
        ),
        sale(
            "line-3",
            basket="basket-2",
            customer_id="customer-2",
            product_id="product-1",
            location_id="location-2",
            business_date=january,
            currency="USD",
            channel="mobile",
            quantity=1,
            net="30.00",
            rejected=True,
        ),
        sale(
            "line-4",
            basket="basket-3",
            customer_id="customer-1",
            product_id="product-1",
            location_id="location-1",
            business_date=january,
            currency="EUR",
            channel="physical",
            quantity=1,
            net="70.00",
        ),
        sale(
            "line-5",
            basket="basket-4",
            customer_id="customer-2",
            product_id="product-1",
            location_id="location-2",
            business_date=february,
            currency="USD",
            channel="mobile",
            quantity=1,
            net="40.00",
        ),
        AnalyticalRecord(
            "bridge_sales_promotion",
            {"transaction_line_id": "line-1", "promotion_id": "promotion-1"},
        ),
        AnalyticalRecord(
            "bridge_sales_promotion",
            {"transaction_line_id": "line-1", "promotion_id": "promotion-2"},
        ),
        AnalyticalRecord(
            "fact_replenishment",
            {
                "replenishment_id": "replenishment-1",
                "inventory_id": "inventory-1",
                "location_id": "location-1",
                "product_id": "product-1",
                "created_date": january,
                "completed_date": february,
                "requested_quantity": 10,
                "received_quantity": 7,
                "requested_tick_index": 1,
                "due_tick_index": 2,
                "completed_tick_index": 3,
                "created_at": datetime(2024, 1, 31),
                "completed_at": datetime(2024, 2, 1),
                "status": "completed",
            },
        ),
        AnalyticalRecord(
            "fact_replenishment",
            {
                "replenishment_id": "replenishment-2",
                "inventory_id": "inventory-2",
                "location_id": "location-2",
                "product_id": "product-2",
                "created_date": february,
                "completed_date": None,
                "requested_quantity": 5,
                "received_quantity": None,
                "requested_tick_index": 4,
                "due_tick_index": 6,
                "completed_tick_index": None,
                "created_at": datetime(2024, 2, 1),
                "completed_at": None,
                "status": "pending",
            },
        ),
        AnalyticalRecord(
            "fact_inventory_movement",
            {
                "movement_id": "movement-1",
                "inventory_id": "inventory-1",
                "location_id": "location-1",
                "product_id": "product-1",
                "transaction_id": "transaction-line-1",
                "basket_id": "basket-1",
                "replenishment_id": None,
                "date": january,
                "movement_type": "sale",
                "quantity": 2,
                "stock_before": 10,
                "stock_after": 8,
                "tick_index": 1,
                "occurred_at": datetime(2024, 1, 31),
            },
        ),
        AnalyticalRecord(
            "fact_inventory_movement",
            {
                "movement_id": "movement-2",
                "inventory_id": "inventory-1",
                "location_id": "location-1",
                "product_id": "product-1",
                "transaction_id": None,
                "basket_id": None,
                "replenishment_id": "replenishment-1",
                "date": february,
                "movement_type": "replenishment",
                "quantity": 7,
                "stock_before": 3,
                "stock_after": 10,
                "tick_index": 3,
                "occurred_at": datetime(2024, 2, 1),
            },
        ),
    )


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    sink = DuckDBAnalyticalSink(":memory:")
    sink.write_batch(analytical_fixture())
    yield sink.connection
    sink.close()


def test_revenue_by_location_excludes_rejected_and_separates_currency(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    rows = run_business_query(connection, BusinessQuery.REVENUE_BY_LOCATION)
    by_key = {(row["location_id"], row["currency"]): row for row in rows}
    assert by_key[("location-1", "USD")]["net_sales"] == Decimal("140.0000")
    assert by_key[("location-1", "USD")]["completed_baskets"] == 1
    assert by_key[("location-1", "EUR")]["net_sales"] == Decimal("70.0000")
    assert by_key[("location-2", "USD")]["net_sales"] == Decimal("40.0000")


def test_product_and_category_keep_realized_and_lost_sales_separate(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    products = run_business_query(connection, BusinessQuery.PRODUCT_PERFORMANCE)
    product_rows = {(row["product_id"], row["currency"]): row for row in products}
    first = product_rows[("product-1", "USD")]
    assert first["completed_units"] == 3
    assert first["net_sales"] == Decimal("130.0000")
    assert first["rejected_units"] == 1
    assert first["lost_sales"] == Decimal("30.0000")
    categories = run_business_query(connection, BusinessQuery.CATEGORY_PERFORMANCE)
    usd = next(row for row in categories if row["currency"] == "USD")
    assert usd["net_sales"] == Decimal("180.0000")
    assert usd["lost_sales"] == Decimal("30.0000")


def test_daily_and_monthly_sales_use_dim_date(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    daily = run_business_query(connection, BusinessQuery.DAILY_SALES)
    by_key = {(row["date"], row["currency"]): row for row in daily}
    assert by_key[(date(2024, 1, 31), "USD")]["net_sales"] == Decimal("140.0000")
    assert by_key[(date(2024, 2, 1), "USD")]["net_sales"] == Decimal("40.0000")
    monthly = run_business_query(connection, BusinessQuery.MONTHLY_SALES)
    assert {(row["month_number"], row["currency"]) for row in monthly} == {
        (1, "EUR"),
        (1, "USD"),
        (2, "USD"),
    }


def test_lost_sales_queries_preserve_reason_product_and_location(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    product_rows = run_business_query(connection, BusinessQuery.LOST_SALES_BY_PRODUCT)
    location_rows = run_business_query(connection, BusinessQuery.LOST_SALES_BY_LOCATION)
    combined = run_business_query(
        connection, BusinessQuery.LOST_SALES_BY_PRODUCT_LOCATION
    )
    reasons = run_business_query(connection, BusinessQuery.LOST_SALES_BY_REASON)
    assert product_rows[0]["product_id"] == "product-1"
    assert location_rows[0]["location_id"] == "location-2"
    assert combined[0]["rejected_quantity"] == 1
    assert reasons[0]["rejection_reason"] == "insufficient_stock"
    assert reasons[0]["lost_sales"] == Decimal("30.0000")


def test_customer_and_channel_basket_counts_are_distinct(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    customers = run_business_query(connection, BusinessQuery.CUSTOMER_PURCHASE_ANALYSIS)
    customer_rows = {(row["customer_id"], row["currency"]): row for row in customers}
    assert customer_rows[("customer-1", "USD")]["basket_count"] == 1
    assert customer_rows[("customer-1", "USD")]["completed_units"] == 3
    channels = run_business_query(connection, BusinessQuery.CHANNEL_PERFORMANCE)
    channel_rows = {(row["channel"], row["currency"]): row for row in channels}
    assert channel_rows[("physical", "USD")]["baskets"] == 1
    assert channel_rows[("mobile", "USD")]["baskets"] == 2


def test_replenishment_and_inventory_movement_questions(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    replenishment = run_business_query(
        connection, BusinessQuery.REPLENISHMENT_PERFORMANCE
    )[0]
    assert replenishment["requested_count"] == 2
    assert replenishment["completed_count"] == 1
    assert replenishment["pending_count"] == 1
    assert replenishment["requested_quantity"] == 15
    assert replenishment["received_quantity"] == 7
    assert replenishment["avg_completion_lead_ticks"] == 2.0
    movements = run_business_query(connection, BusinessQuery.INVENTORY_MOVEMENT_SUMMARY)
    by_type = {row["movement_type"]: row for row in movements}
    assert by_type["sale"]["quantity_removed_by_sales"] == 2
    assert by_type["replenishment"]["quantity_received_by_replenishment"] == 7
    assert run_business_query(connection, BusinessQuery.INVENTORY_MOVEMENT_BY_PRODUCT)
    assert run_business_query(connection, BusinessQuery.INVENTORY_MOVEMENT_BY_LOCATION)


def test_promotion_summary_deduplicates_lines_while_per_promotion_can_overlap(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    summary = run_business_query(connection, BusinessQuery.PROMOTED_SALES_SUMMARY)[0]
    assert summary["associated_sales_lines"] == 1
    assert summary["associated_net_sales"] == Decimal("90.0000")
    per_promotion = run_business_query(
        connection, BusinessQuery.PROMOTION_ASSOCIATED_SALES
    )
    assert len(per_promotion) == 2
    assert all(
        row["associated_net_sales"] == Decimal("90.0000") for row in per_promotion
    )
