"""Explicit public configuration for physical operational exports."""

from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path

from dataforge.export.files.csv_sink import CsvOperationalDataSink
from dataforge.export.files.parquet_sink import ParquetOperationalDataSink
from dataforge.export.files.routing import expected_output_paths
from dataforge.export.operational.model import OperationalDataModel
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.export.operational.sink import OperationalDataSink, OperationalRecord


class ExportFormat(StrEnum):
    CSV = "csv"
    PARQUET = "parquet"
    BOTH = "both"


class CompositeOperationalDataSink:
    """Fan out one bounded lifecycle phase to multiple synchronous sinks."""

    def __init__(self, sinks: Iterable[OperationalDataSink]) -> None:
        self._sinks = tuple(sinks)
        if not self._sinks:
            raise ValueError("Composite sink requires at least one sink")

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self._write("master", None, records)

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        self._write("tick", tick_index, records)

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self._write("final", None, records)

    def close(self) -> None:
        first_error: Exception | None = None
        for sink in self._sinks:
            try:
                sink.close()
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def _write(
        self,
        phase: str,
        tick_index: int | None,
        records: Iterable[OperationalRecord],
    ) -> None:
        phase_records = tuple(records)
        for sink in self._sinks:
            if phase == "master":
                sink.write_master(phase_records)
            elif phase == "tick":
                if tick_index is None:
                    raise ValueError("Tick output requires a tick index")
                sink.write_tick(tick_index, phase_records)
            else:
                sink.write_final(phase_records)


def build_export_sink(
    export_format: ExportFormat,
    output_directory: Path,
) -> OperationalDataSink:
    """Preflight all targets, then build the explicitly supported sink layout."""
    model = build_operational_data_model()
    if export_format is ExportFormat.CSV:
        _preflight(((output_directory, "csv"),), model)
        return CsvOperationalDataSink(output_directory, model=model)
    if export_format is ExportFormat.PARQUET:
        _preflight(((output_directory, "parquet"),), model)
        return ParquetOperationalDataSink(output_directory, model=model)

    csv_directory = output_directory / "csv"
    parquet_directory = output_directory / "parquet"
    _preflight(((csv_directory, "csv"), (parquet_directory, "parquet")), model)
    return CompositeOperationalDataSink(
        (
            CsvOperationalDataSink(csv_directory, model=model),
            ParquetOperationalDataSink(parquet_directory, model=model),
        )
    )


def export_dataset_count() -> int:
    return len(build_operational_data_model().datasets)


def _preflight(
    targets: tuple[tuple[Path, str], ...],
    model: OperationalDataModel,
) -> None:
    existing = tuple(
        path
        for directory, extension in targets
        for path in expected_output_paths(directory, model, extension).values()
        if path.exists()
    )
    if existing:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Operational output already exists: {names}")
