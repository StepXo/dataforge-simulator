"""Incremental Parquet operational data sink."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from dataforge.export.files.routing import (
    BufferedDatasetRouter,
    OrderedRow,
    prepare_output_files,
)
from dataforge.export.operational.model import (
    DatasetDefinition,
    LogicalDataType,
    OperationalDataModel,
)
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.export.operational.sink import OperationalRecord

_DECIMAL_PRECISION = 38
_DECIMAL_SCALE = 4


class ParquetOperationalDataSink:
    """Write bounded record batches to one Parquet file per ODM dataset."""

    def __init__(
        self,
        output_directory: Path,
        *,
        model: OperationalDataModel | None = None,
        batch_size: int = 1000,
        compression: str = "snappy",
    ) -> None:
        self._model = model or build_operational_data_model()
        self._paths = prepare_output_files(output_directory, self._model, "parquet")
        self._batch_size = batch_size
        self._compression = compression
        self._writers: dict[str, pq.ParquetWriter] = {}
        self._schemas: dict[str, pa.Schema] = {}
        self._timezones: dict[str, str | None] = {}
        self._closed = False
        self._router = BufferedDatasetRouter(self._model, batch_size, self._write_rows)

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self._write(records)

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        del tick_index
        self._write(records)

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self._write(records)

    def close(self) -> None:
        if self._closed:
            return
        self._router.flush_all()
        for dataset in self._model.datasets:
            self._require_writer(dataset)
        for writer in self._writers.values():
            writer.close()
        self._closed = True

    def _write(self, records: Iterable[OperationalRecord]) -> None:
        if self._closed:
            raise ValueError("Parquet operational sink is closed")
        self._router.consume(records)

    def _write_rows(
        self, dataset: DatasetDefinition, rows: tuple[OrderedRow, ...]
    ) -> None:
        timezone = _rows_timezone(dataset, rows)
        known_timezone = self._timezones.get(dataset.name)
        if dataset.name in self._timezones and timezone != known_timezone:
            raise ValueError(
                f"Datetime timezone changed within dataset: {dataset.name}"
            )
        if dataset.name not in self._timezones:
            self._timezones[dataset.name] = timezone
        writer = self._require_writer(dataset)
        schema = self._schemas[dataset.name]
        arrays = [
            pa.array((row[index] for row in rows), type=field.type)
            for index, field in enumerate(schema)
        ]
        writer.write_table(pa.Table.from_arrays(arrays, schema=schema))

    def _require_writer(self, dataset: DatasetDefinition) -> pq.ParquetWriter:
        writer = self._writers.get(dataset.name)
        if writer is None:
            schema = arrow_schema_from_dataset(
                dataset, timezone=self._timezones.get(dataset.name)
            )
            writer = pq.ParquetWriter(
                self._paths[dataset.name],
                schema,
                compression=self._compression,
            )
            self._writers[dataset.name] = writer
            self._schemas[dataset.name] = schema
        return writer


def arrow_schema_from_dataset(
    dataset: DatasetDefinition,
    *,
    timezone: str | None = None,
) -> pa.Schema:
    """Derive one Arrow schema exclusively from an ODM dataset definition."""
    return pa.schema(
        pa.field(
            column.name,
            _arrow_type(column.logical_type, timezone),
            nullable=column.nullable,
        )
        for column in dataset.columns
    )


def _arrow_type(logical_type: LogicalDataType, timezone: str | None) -> pa.DataType:
    match logical_type:
        case LogicalDataType.STRING:
            return pa.string()
        case LogicalDataType.INTEGER:
            return pa.int64()
        case LogicalDataType.DECIMAL:
            return pa.decimal128(_DECIMAL_PRECISION, _DECIMAL_SCALE)
        case LogicalDataType.FLOAT:
            return pa.float64()
        case LogicalDataType.BOOLEAN:
            return pa.bool_()
        case LogicalDataType.DATE:
            return pa.date32()
        case LogicalDataType.DATETIME:
            return pa.timestamp("us", tz=timezone)
    raise ValueError(f"Unsupported logical data type: {logical_type}")


def _rows_timezone(
    dataset: DatasetDefinition, rows: tuple[OrderedRow, ...]
) -> str | None:
    timezones: set[str | None] = set()
    for index, column in enumerate(dataset.columns):
        if column.logical_type is not LogicalDataType.DATETIME:
            continue
        for row in rows:
            value = row[index]
            if isinstance(value, datetime):
                timezones.add(_timezone_name(value))
    if len(timezones) > 1:
        raise ValueError(f"Mixed datetime timezones in dataset: {dataset.name}")
    return next(iter(timezones), None)


def _timezone_name(value: datetime) -> str | None:
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    key = getattr(value.tzinfo, "key", None)
    return str(key if key is not None else value.tzinfo)
