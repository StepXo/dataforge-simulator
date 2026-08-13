"""Incremental DuckDB storage for the DataForge Analytical Model."""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import duckdb
import pyarrow as pa

from dataforge.analytics.builder import AnalyticalDataBuilder
from dataforge.analytics.model import (
    AnalyticalDatasetDefinition,
    AnalyticalModel,
    AnalyticalRecord,
)
from dataforge.analytics.schema import build_analytical_model
from dataforge.export.operational.model import LogicalDataType
from dataforge.export.operational.sink import OperationalDataSink, OperationalRecord

type DuckDBTarget = str | Path | duckdb.DuckDBPyConnection
_DECIMAL_PRECISION = 38
_DECIMAL_SCALE = 4


class DuckDBAnalyticalSink:
    """Create and batch-load one DuckDB table per analytical dataset."""

    def __init__(
        self,
        target: DuckDBTarget,
        *,
        model: AnalyticalModel | None = None,
    ) -> None:
        self._model = model or build_analytical_model()
        self._owns_connection = isinstance(target, (str, Path))
        if isinstance(target, (str, Path)):
            database = str(target)
            if database != ":memory:":
                path = Path(database)
                if path.exists():
                    raise FileExistsError(f"DuckDB analytical output exists: {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = duckdb.connect(database)
        else:
            self._connection = target
        self._closed = False
        try:
            self._create_tables()
        except Exception:
            if self._owns_connection:
                self._connection.close()
            raise

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Expose the live connection for local analytical queries."""
        if self._closed:
            raise ValueError("DuckDB analytical sink is closed")
        return self._connection

    def write_batch(self, records: Iterable[AnalyticalRecord]) -> None:
        """Write one bounded logical batch atomically using Arrow tables."""
        self._require_open()
        grouped: dict[str, list[AnalyticalRecord]] = defaultdict(list)
        for record in records:
            self._model.require_dataset(record.dataset)
            grouped[record.dataset].append(record)
        if not grouped:
            return

        self._connection.execute("BEGIN TRANSACTION")
        try:
            for dataset in self._model.datasets:
                rows = grouped.get(dataset.name)
                if rows:
                    self._insert(dataset, rows)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_connection:
            self._connection.close()
        self._closed = True

    def _create_tables(self) -> None:
        for dataset in self._model.datasets:
            columns = [
                f"{_quote(column.name)} {_duckdb_type(column.logical_type)}"
                f"{'' if column.nullable else ' NOT NULL'}"
                for column in dataset.columns
            ]
            if dataset.primary_key:
                keys = ", ".join(_quote(name) for name in dataset.primary_key)
                columns.append(f"PRIMARY KEY ({keys})")
            sql = f"CREATE TABLE {_quote(dataset.name)} ({', '.join(columns)})"
            self._connection.execute(sql)

    def _insert(
        self,
        dataset: AnalyticalDatasetDefinition,
        records: list[AnalyticalRecord],
    ) -> None:
        names = tuple(column.name for column in dataset.columns)
        expected = set(names)
        for record in records:
            if set(record.values) != expected:
                raise ValueError(
                    f"Analytical record columns do not match schema: {dataset.name}"
                )
        schema = pa.schema(
            pa.field(
                column.name,
                _arrow_type(column.logical_type),
                nullable=column.nullable,
            )
            for column in dataset.columns
        )
        arrays = [
            pa.array(
                (record.values[name] for record in records),
                type=schema.field(name).type,
            )
            for name in names
        ]
        table = pa.Table.from_arrays(arrays, schema=schema)
        view_name = f"_dataforge_{dataset.name}_batch"
        self._connection.register(view_name, table)
        try:
            columns = ", ".join(_quote(name) for name in names)
            self._connection.execute(
                f"INSERT INTO {_quote(dataset.name)} ({columns}) "
                f"SELECT {columns} FROM {_quote(view_name)}"
            )
        finally:
            self._connection.unregister(view_name)

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("DuckDB analytical sink is closed")


class DuckDBOperationalAnalyticsSink(OperationalDataSink):
    """Transform lifecycle-ordered ODM batches and load them into DuckDB."""

    def __init__(self, sink: DuckDBAnalyticalSink) -> None:
        self._sink = sink
        self._builder = AnalyticalDataBuilder()

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self._write(records)

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        del tick_index
        self._write(records)

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self._write(records)

    def close(self) -> None:
        self._sink.close()

    def _write(self, records: Iterable[OperationalRecord]) -> None:
        self._sink.write_batch(self._builder.transform(records))


def _quote(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _duckdb_type(logical_type: LogicalDataType) -> str:
    match logical_type:
        case LogicalDataType.STRING:
            return "VARCHAR"
        case LogicalDataType.INTEGER:
            return "BIGINT"
        case LogicalDataType.DECIMAL:
            return f"DECIMAL({_DECIMAL_PRECISION}, {_DECIMAL_SCALE})"
        case LogicalDataType.FLOAT:
            return "DOUBLE"
        case LogicalDataType.BOOLEAN:
            return "BOOLEAN"
        case LogicalDataType.DATE:
            return "DATE"
        case LogicalDataType.DATETIME:
            return "TIMESTAMP"
    raise ValueError(f"Unsupported analytical logical type: {logical_type}")


def _arrow_type(logical_type: LogicalDataType) -> pa.DataType:
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
            return pa.timestamp("us")
    raise ValueError(f"Unsupported analytical logical type: {logical_type}")


__all__ = ["DuckDBAnalyticalSink", "DuckDBOperationalAnalyticsSink"]
