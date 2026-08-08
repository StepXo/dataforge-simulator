"""Tests for the shared incremental CSV and Parquet file sinks."""

import csv
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dataforge.export.files.csv_sink import CsvOperationalDataSink
from dataforge.export.files.parquet_sink import (
    ParquetOperationalDataSink,
    arrow_schema_from_dataset,
)
from dataforge.export.operational.model import (
    ColumnDefinition,
    DatasetDefinition,
    LogicalDataType,
    OperationalDataModel,
)
from dataforge.export.operational.sink import OperationalRecord


def model() -> OperationalDataModel:
    return OperationalDataModel(
        datasets=(
            DatasetDefinition(
                name="facts",
                columns=(
                    ColumnDefinition("id", LogicalDataType.STRING),
                    ColumnDefinition("amount", LogicalDataType.DECIMAL),
                    ColumnDefinition("occurred_at", LogicalDataType.DATETIME),
                    ColumnDefinition("business_date", LogicalDataType.DATE),
                    ColumnDefinition("active", LogicalDataType.BOOLEAN),
                ),
                primary_key=("id",),
            ),
            DatasetDefinition(
                name="empty",
                columns=(ColumnDefinition("id", LogicalDataType.INTEGER),),
                primary_key=("id",),
            ),
        )
    )


def record(index: int) -> OperationalRecord:
    return OperationalRecord(
        "facts",
        {
            "id": f"fact-{index}",
            "amount": Decimal("12.3400"),
            "occurred_at": datetime(2026, 8, 7, 12, index),
            "business_date": date(2026, 8, 7),
            "active": index % 2 == 0,
        },
    )


def test_arrow_schema_is_derived_from_odm() -> None:
    schema = arrow_schema_from_dataset(model().require_dataset("facts"), timezone="UTC")

    assert schema.names == ["id", "amount", "occurred_at", "business_date", "active"]
    assert schema.field("id").type == pa.string()
    assert pa.types.is_decimal(schema.field("amount").type)
    assert schema.field("occurred_at").type == pa.timestamp("us", tz="UTC")
    assert schema.field("business_date").type == pa.date32()
    assert schema.field("active").type == pa.bool_()


def test_parquet_roundtrip_empty_dataset_and_batch_flushing(tmp_path: Path) -> None:
    sink = ParquetOperationalDataSink(tmp_path, model=model(), batch_size=2)
    sink.write_master(record(index) for index in range(5))
    sink.close()

    table = pq.read_table(tmp_path / "facts.parquet")
    empty = pq.read_table(tmp_path / "empty.parquet")
    metadata = pq.ParquetFile(tmp_path / "facts.parquet").metadata
    assert table.num_rows == 5
    assert table.column("amount").to_pylist() == [Decimal("12.3400")] * 5
    assert table.column("occurred_at").to_pylist()[0] == datetime(2026, 8, 7, 12, 0)
    assert empty.num_rows == 0
    assert metadata.num_row_groups == 3
    assert metadata.row_group(0).column(0).compression == "SNAPPY"


def test_parquet_preserves_timezone_metadata(tmp_path: Path) -> None:
    aware = record(0)
    aware_values = dict(aware.values)
    aware_values["occurred_at"] = datetime(2026, 8, 7, 12, tzinfo=UTC)
    sink = ParquetOperationalDataSink(tmp_path, model=model())
    sink.write_master([OperationalRecord("facts", aware_values)])
    sink.close()

    assert pq.read_schema(tmp_path / "facts.parquet").field("occurred_at").type == (
        pa.timestamp("us", tz="UTC")
    )


def test_csv_headers_order_values_and_empty_dataset(tmp_path: Path) -> None:
    sink = CsvOperationalDataSink(tmp_path, model=model(), batch_size=2)
    sink.write_master([record(0)])
    sink.close()

    with (tmp_path / "facts.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    with (tmp_path / "empty.csv").open(encoding="utf-8", newline="") as file:
        empty_rows = list(csv.reader(file))
    assert rows == [
        ["id", "amount", "occurred_at", "business_date", "active"],
        ["fact-0", "12.3400", "2026-08-07T12:00:00", "2026-08-07", "true"],
    ]
    assert empty_rows == [["id"]]


@pytest.mark.parametrize(
    "sink_type", [CsvOperationalDataSink, ParquetOperationalDataSink]
)
def test_existing_expected_file_fails_before_export(
    tmp_path: Path,
    sink_type: type[CsvOperationalDataSink] | type[ParquetOperationalDataSink],
) -> None:
    (
        tmp_path
        / ("facts.csv" if sink_type is CsvOperationalDataSink else "facts.parquet")
    ).write_text("existing")

    with pytest.raises(FileExistsError, match="facts"):
        sink_type(tmp_path, model=model())
