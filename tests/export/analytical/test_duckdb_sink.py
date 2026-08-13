"""DuckDB analytical schema and bounded batch loading tests."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from dataforge.analytics import (
    AnalyticalDataBuilder,
    AnalyticalRecord,
    build_analytical_model,
)
from dataforge.export.analytical import DuckDBAnalyticalSink
from tests.analytics.test_builder import master_records, transaction_records


def analytical_records() -> tuple[AnalyticalRecord, ...]:
    return tuple(
        AnalyticalDataBuilder().transform((*master_records(), *transaction_records()))
    )


def test_schema_is_created_from_every_analytical_dataset() -> None:
    sink = DuckDBAnalyticalSink(":memory:")

    tables = {row[0] for row in sink.connection.execute("SHOW TABLES").fetchall()}
    assert tables == {
        "dim_date",
        "dim_customer",
        "dim_product",
        "dim_location",
        "dim_promotion",
        "fact_sales",
        "fact_inventory_movement",
        "fact_replenishment",
        "bridge_sales_promotion",
    }
    for dataset in build_analytical_model().datasets:
        actual = tuple(
            row[1]
            for row in sink.connection.execute(
                f"PRAGMA table_info('{dataset.name}')"
            ).fetchall()
        )
        assert actual == tuple(column.name for column in dataset.columns)
    columns = {
        row[1]: row[2]
        for row in sink.connection.execute("PRAGMA table_info('fact_sales')").fetchall()
    }
    assert columns["net_sales_amount"] == "DECIMAL(38,4)"
    assert columns["occurred_at"] == "TIMESTAMP"
    assert columns["date"] == "DATE"
    sink.close()


def test_batch_writes_multiple_datasets_successive_batches_and_empty_batch() -> None:
    sink = DuckDBAnalyticalSink(":memory:")
    records = analytical_records()
    first = tuple(record for record in records if record.dataset.startswith("dim_"))
    second = tuple(record for record in records if record.dataset == "fact_sales")

    sink.write_batch(first)
    sink.write_batch(())
    sink.write_batch(second)

    assert sink.connection.execute("SELECT count(*) FROM dim_customer").fetchone() == (
        1,
    )
    row = sink.connection.execute(
        "SELECT net_sales_amount, rejection_reason FROM fact_sales"
    ).fetchone()
    assert row == (Decimal("45.0000"), None)
    sink.close()


def test_rejected_sales_nullable_fields_and_bridge_grain_are_preserved() -> None:
    builder = AnalyticalDataBuilder()
    records = tuple(builder.transform(transaction_records("rejected")))
    sales = tuple(record for record in records if record.dataset == "fact_sales")
    bridge = (
        AnalyticalRecord(
            "bridge_sales_promotion",
            {"transaction_line_id": "line", "promotion_id": "promotion-1"},
        ),
        AnalyticalRecord(
            "bridge_sales_promotion",
            {"transaction_line_id": "line", "promotion_id": "promotion-2"},
        ),
    )
    sink = DuckDBAnalyticalSink(":memory:")
    sink.write_batch((*sales, *bridge))

    fact = sink.connection.execute(
        "SELECT net_sales_amount, lost_sales_amount, rejected_quantity FROM fact_sales"
    ).fetchone()
    assert fact == (Decimal("0.0000"), Decimal("45.0000"), 2)
    assert sink.connection.execute(
        "SELECT count(*) FROM bridge_sales_promotion"
    ).fetchone() == (2,)
    sink.close()


def test_inventory_and_replenishment_traceability_round_trip() -> None:
    occurred_at = datetime(2024, 1, 3, 12, 30)
    records = (
        AnalyticalRecord(
            "fact_replenishment",
            {
                "replenishment_id": "replenishment-1",
                "inventory_id": "inventory-1",
                "location_id": "location-1",
                "product_id": "product-1",
                "created_date": date(2024, 1, 1),
                "completed_date": date(2024, 1, 3),
                "requested_quantity": 10,
                "received_quantity": 7,
                "requested_tick_index": 1,
                "due_tick_index": 2,
                "completed_tick_index": 3,
                "created_at": datetime(2024, 1, 1),
                "completed_at": occurred_at,
                "status": "completed",
            },
        ),
        AnalyticalRecord(
            "fact_inventory_movement",
            {
                "movement_id": "movement-1",
                "inventory_id": "inventory-1",
                "location_id": "location-1",
                "product_id": "product-1",
                "transaction_id": None,
                "basket_id": None,
                "replenishment_id": "replenishment-1",
                "date": date(2024, 1, 3),
                "movement_type": "replenishment",
                "quantity": 7,
                "stock_before": 3,
                "stock_after": 10,
                "tick_index": 3,
                "occurred_at": occurred_at,
            },
        ),
    )
    sink = DuckDBAnalyticalSink(":memory:")
    sink.write_batch(records)

    row = sink.connection.execute(
        "SELECT r.replenishment_id, r.received_quantity, m.quantity, "
        "r.completed_at, m.occurred_at "
        "FROM fact_replenishment r JOIN fact_inventory_movement m "
        "USING (replenishment_id)"
    ).fetchone()
    assert row == ("replenishment-1", 7, 7, occurred_at, occurred_at)
    sink.close()


def test_persistent_database_reopens_with_same_rows(tmp_path: Path) -> None:
    path = tmp_path / "analytics.duckdb"
    sink = DuckDBAnalyticalSink(path)
    sink.write_batch(analytical_records())
    sink.close()

    connection = duckdb.connect(str(path), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM fact_sales").fetchone() == (1,)
    finally:
        connection.close()
    with pytest.raises(FileExistsError):
        DuckDBAnalyticalSink(path)


def test_failed_batch_rolls_back_every_dataset_in_that_batch() -> None:
    sink = DuckDBAnalyticalSink(":memory:")
    calendar = AnalyticalRecord(
        "dim_date",
        {
            "date": date(2024, 1, 1),
            "year": 2024,
            "quarter": 1,
            "month_number": 1,
            "month_name": "January",
            "iso_week": 1,
            "iso_week_year": 2024,
            "iso_weekday": 1,
            "weekday_name": "Monday",
            "weekend": False,
        },
    )
    customer = tuple(
        record for record in analytical_records() if record.dataset == "dim_customer"
    )[0]
    sink.write_batch((customer,))

    with pytest.raises(duckdb.ConstraintException):
        sink.write_batch((calendar, customer))

    assert sink.connection.execute("SELECT count(*) FROM dim_date").fetchone() == (0,)
    sink.close()
