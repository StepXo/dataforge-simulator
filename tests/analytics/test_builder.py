"""Incremental ODM-to-analytical transformation tests."""

from datetime import date, datetime
from decimal import Decimal

from dataforge.analytics import AnalyticalDataBuilder, AnalyticalRecord
from dataforge.export.operational import OperationalRecord

NOW = datetime(2024, 12, 30, 10, 15)


def master_records() -> tuple[OperationalRecord, ...]:
    return (
        OperationalRecord(
            "countries", {"country_id": "co", "code": "CO", "name": "Country"}
        ),
        OperationalRecord(
            "regions", {"region_id": "r", "name": "Region", "country_id": "co"}
        ),
        OperationalRecord(
            "administrative_areas",
            {
                "administrative_area_id": "a",
                "name": "Area",
                "area_type": "state",
                "region_id": "r",
                "country_id": "co",
            },
        ),
        OperationalRecord(
            "cities",
            {
                "city_id": "c",
                "name": "City",
                "administrative_area_id": "a",
                "region_id": "r",
                "country_id": "co",
            },
        ),
        OperationalRecord(
            "locations",
            {
                "location_id": "l",
                "name": "Location",
                "city_id": "c",
                "administrative_area_id": "a",
                "region_id": "r",
                "country_id": "co",
                "capacity": 10,
                "activity_factor": 1.2,
                "opened_at": date(2020, 1, 1),
            },
        ),
        OperationalRecord("categories", {"category_id": "cat", "name": "Category"}),
        OperationalRecord(
            "products",
            {
                "product_id": "p",
                "name": "Product",
                "category_id": "cat",
                "currency": "CUR",
                "base_price": Decimal("25.00"),
                "base_cost": Decimal("10.00"),
                "base_margin": Decimal("15.00"),
                "activity_factor": 1.0,
                "active": True,
            },
        ),
        OperationalRecord(
            "customers",
            {
                "customer_id": "cu",
                "home_city_id": "c",
                "home_region_id": "r",
                "preferred_location_id": "l",
                "segment": "regular",
                "purchase_frequency": 10.0,
                "preferred_channel": "physical",
                "promotion_sensitivity": 0.5,
                "activity_factor": 1.0,
                "registered_at": date(2024, 1, 1),
                "active": True,
            },
        ),
        OperationalRecord(
            "promotions",
            {
                "promotion_id": "promo",
                "name": "Promotion",
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 12, 31),
                "target_type": "global",
                "channel": "all",
                "discount_rate": 0.1,
                "demand_lift": 1.1,
                "active": True,
            },
        ),
    )


def transaction_records(status: str = "completed") -> tuple[OperationalRecord, ...]:
    completed = status == "completed"
    return (
        OperationalRecord(
            "transactions",
            {
                "transaction_id": "t",
                "basket_id": "b",
                "customer_id": "cu",
                "location_id": "l",
                "channel": "physical",
                "currency": "CUR",
                "gross_amount": Decimal("50.00") if completed else Decimal("0.00"),
                "discount_amount": Decimal("5.00") if completed else Decimal("0.00"),
                "net_amount": Decimal("45.00") if completed else Decimal("0.00"),
                "lost_sales_amount": Decimal("0.00") if completed else Decimal("45.00"),
                "completed_units": 2 if completed else 0,
                "rejected_units": 0 if completed else 2,
                "status": status,
                "tick_index": 0,
                "occurred_at": NOW,
            },
        ),
        OperationalRecord(
            "transaction_lines",
            {
                "transaction_line_id": "line",
                "transaction_id": "t",
                "intent_id": "i",
                "quote_intent_id": "q",
                "product_id": "p",
                "quantity": 2,
                "unit_price": Decimal("25.00"),
                "gross_amount": Decimal("50.00"),
                "discount_amount": Decimal("5.00"),
                "net_amount": Decimal("45.00"),
                "status": status,
                "rejection_reason": None if completed else "insufficient_stock",
            },
        ),
    )


def by_dataset(
    records: tuple[AnalyticalRecord, ...], name: str
) -> tuple[AnalyticalRecord, ...]:
    return tuple(item for item in records if item.dataset == name)


def test_dimensions_flatten_geography_and_category_and_dates() -> None:
    records = tuple(
        AnalyticalDataBuilder().transform((*master_records(), *transaction_records()))
    )
    location = by_dataset(records, "dim_location")[0].values
    product = by_dataset(records, "dim_product")[0].values
    calendar = by_dataset(records, "dim_date")[0].values
    assert (
        location["country_name"],
        location["region_name"],
        location["city_name"],
    ) == ("Country", "Region", "City")
    assert product["category_name"] == "Category"
    assert calendar == {
        "date": date(2024, 12, 30),
        "year": 2024,
        "quarter": 4,
        "month_number": 12,
        "month_name": "December",
        "iso_week": 1,
        "iso_week_year": 2025,
        "iso_weekday": 1,
        "weekday_name": "Monday",
        "weekend": False,
    }


def test_completed_and_rejected_sales_have_mutually_exclusive_measures() -> None:
    completed = by_dataset(
        tuple(AnalyticalDataBuilder().transform(transaction_records())), "fact_sales"
    )[0].values
    rejected = by_dataset(
        tuple(AnalyticalDataBuilder().transform(transaction_records("rejected"))),
        "fact_sales",
    )[0].values
    assert completed["completed_quantity"] == 2 and completed["rejected_quantity"] == 0
    assert completed["net_sales_amount"] == Decimal("45.00")
    assert completed["lost_sales_amount"] == Decimal("0.00")
    assert rejected["completed_quantity"] == 0 and rejected["rejected_quantity"] == 2
    assert rejected["gross_sales_amount"] == Decimal("0.00")
    assert rejected["discount_amount"] == Decimal("0.00")
    assert rejected["net_sales_amount"] == Decimal("0.00")
    assert rejected["lost_sales_amount"] == Decimal("45.00")


def test_multiple_promotions_do_not_duplicate_fact_sales() -> None:
    records = (
        *transaction_records(),
        OperationalRecord(
            "transaction_line_promotions",
            {"transaction_line_id": "line", "promotion_id": "p1"},
        ),
        OperationalRecord(
            "transaction_line_promotions",
            {"transaction_line_id": "line", "promotion_id": "p2"},
        ),
    )
    transformed = tuple(AnalyticalDataBuilder().transform(records))
    assert len(by_dataset(transformed, "fact_sales")) == 1
    assert len(by_dataset(transformed, "bridge_sales_promotion")) == 2


def test_zero_and_one_promotion_preserve_one_sales_fact() -> None:
    without = tuple(AnalyticalDataBuilder().transform(transaction_records()))
    with_one = tuple(
        AnalyticalDataBuilder().transform(
            (
                *transaction_records(),
                OperationalRecord(
                    "transaction_line_promotions",
                    {"transaction_line_id": "line", "promotion_id": "promo"},
                ),
            )
        )
    )
    assert len(by_dataset(without, "fact_sales")) == 1
    assert by_dataset(without, "bridge_sales_promotion") == ()
    assert len(by_dataset(with_one, "fact_sales")) == 1
    assert len(by_dataset(with_one, "bridge_sales_promotion")) == 1


def test_inventory_and_replenishment_preserve_physical_traceability() -> None:
    records = (
        OperationalRecord(
            "inventory_movements",
            {
                "movement_id": "m",
                "inventory_id": "inv",
                "location_id": "l",
                "product_id": "p",
                "transaction_id": None,
                "basket_id": None,
                "replenishment_id": "rep",
                "movement_type": "replenishment",
                "quantity": 7,
                "stock_before": 3,
                "stock_after": 10,
                "tick_index": 2,
                "occurred_at": NOW,
            },
        ),
        OperationalRecord(
            "replenishments",
            {
                "replenishment_id": "rep",
                "inventory_id": "inv",
                "location_id": "l",
                "product_id": "p",
                "requested_quantity": 8,
                "requested_tick_index": 1,
                "due_tick_index": 1,
                "created_at": datetime(2024, 12, 29),
                "status": "completed",
                "completed_tick_index": 2,
                "completed_at": NOW,
                "received_quantity": 7,
            },
        ),
    )
    transformed = tuple(AnalyticalDataBuilder().transform(records))
    movement = by_dataset(transformed, "fact_inventory_movement")[0].values
    replenishment = by_dataset(transformed, "fact_replenishment")[0].values
    assert movement["replenishment_id"] == replenishment["replenishment_id"] == "rep"
    assert replenishment["requested_quantity"] == 8
    assert replenishment["received_quantity"] == 7
    assert replenishment["due_tick_index"] == 1
    assert replenishment["completed_tick_index"] == 2


def test_sale_movement_preserves_transaction_and_stock_values() -> None:
    record = OperationalRecord(
        "inventory_movements",
        {
            "movement_id": "sale-movement",
            "inventory_id": "inv",
            "location_id": "l",
            "product_id": "p",
            "transaction_id": "transaction",
            "basket_id": "basket",
            "replenishment_id": None,
            "movement_type": "sale",
            "quantity": 2,
            "stock_before": 10,
            "stock_after": 8,
            "tick_index": 2,
            "occurred_at": NOW,
        },
    )
    fact = by_dataset(
        tuple(AnalyticalDataBuilder().transform((record,))),
        "fact_inventory_movement",
    )[0].values
    assert fact["transaction_id"] == "transaction"
    assert fact["replenishment_id"] is None
    assert (fact["stock_before"], fact["stock_after"], fact["quantity"]) == (10, 8, 2)


def test_pending_replenishment_keeps_completion_nullable() -> None:
    record = OperationalRecord(
        "replenishments",
        {
            "replenishment_id": "rep",
            "inventory_id": "inv",
            "location_id": "l",
            "product_id": "p",
            "requested_quantity": 8,
            "requested_tick_index": 1,
            "due_tick_index": 3,
            "created_at": NOW,
            "status": "pending",
            "completed_tick_index": None,
            "completed_at": None,
            "received_quantity": None,
        },
    )
    fact = by_dataset(
        tuple(AnalyticalDataBuilder().transform((record,))), "fact_replenishment"
    )[0]
    assert fact.values["completed_tick_index"] is None
    assert fact.values["completed_at"] is None
    assert fact.values["received_quantity"] is None


def test_complete_and_incremental_inputs_produce_same_logical_records() -> None:
    source = (
        *master_records(),
        *transaction_records(),
        OperationalRecord("metrics", {"current_time": NOW}),
    )
    complete = tuple(AnalyticalDataBuilder().transform(source))
    incremental_builder = AnalyticalDataBuilder()
    incremental = tuple(
        item
        for batch in (source[:5], source[5:9], source[9:])
        for item in incremental_builder.transform(batch)
    )
    assert incremental == complete


def test_dim_date_deduplicates_dates_and_marks_weekends() -> None:
    saturday = datetime(2024, 12, 28, 8)
    records = (
        OperationalRecord("metrics", {"current_time": saturday}),
        OperationalRecord("metrics", {"current_time": saturday.replace(hour=9)}),
    )
    dates = by_dataset(tuple(AnalyticalDataBuilder().transform(records)), "dim_date")
    assert len(dates) == 1
    assert dates[0].values["iso_weekday"] == 6
    assert dates[0].values["weekend"] is True
