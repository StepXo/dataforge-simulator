"""Incremental CSV operational data sink."""

import csv
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TextIO

from dataforge.export.files.routing import (
    BufferedDatasetRouter,
    OrderedRow,
    prepare_output_files,
)
from dataforge.export.operational.model import DatasetDefinition, OperationalDataModel
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.export.operational.sink import OperationalRecord, OperationalValue


class _CsvWriter(Protocol):
    def writerow(self, row: Iterable[object]) -> object: ...

    def writerows(self, rows: Iterable[Iterable[object]]) -> None: ...


class CsvOperationalDataSink:
    """Write one incrementally populated CSV file per ODM dataset."""

    def __init__(
        self,
        output_directory: Path,
        *,
        model: OperationalDataModel | None = None,
        batch_size: int = 1000,
    ) -> None:
        self._model = model or build_operational_data_model()
        paths = prepare_output_files(output_directory, self._model, "csv")
        self._files: dict[str, TextIO] = {}
        self._writers: dict[str, _CsvWriter] = {}
        self._closed = False
        try:
            for dataset in self._model.datasets:
                file = paths[dataset.name].open("x", encoding="utf-8", newline="")
                writer = csv.writer(file)
                writer.writerow(column.name for column in dataset.columns)
                self._files[dataset.name] = file
                self._writers[dataset.name] = writer
        except Exception:
            self._close_files()
            raise
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
        self._close_files()
        self._closed = True

    def _write(self, records: Iterable[OperationalRecord]) -> None:
        if self._closed:
            raise ValueError("CSV operational sink is closed")
        self._router.consume(records)

    def _write_rows(
        self, dataset: DatasetDefinition, rows: tuple[OrderedRow, ...]
    ) -> None:
        writer = self._writers[dataset.name]
        writer.writerows(tuple(_csv_value(value) for value in row) for row in rows)

    def _close_files(self) -> None:
        for file in self._files.values():
            file.close()


def _csv_value(value: OperationalValue) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
