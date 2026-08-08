"""Shared format-independent routing for incremental file sinks."""

from collections.abc import Callable, Iterable
from pathlib import Path

from dataforge.export.operational.model import DatasetDefinition, OperationalDataModel
from dataforge.export.operational.sink import OperationalRecord, OperationalValue

OrderedRow = tuple[OperationalValue, ...]
FlushRows = Callable[[DatasetDefinition, tuple[OrderedRow, ...]], None]


def expected_output_paths(
    output_directory: Path,
    model: OperationalDataModel,
    extension: str,
) -> dict[str, Path]:
    """Return every ODM-derived output path without modifying the filesystem."""
    return {
        dataset.name: output_directory / f"{dataset.name}.{extension}"
        for dataset in model.datasets
    }


def prepare_output_files(
    output_directory: Path,
    model: OperationalDataModel,
    extension: str,
) -> dict[str, Path]:
    """Validate overwrite policy and return every ODM-derived output path."""
    paths = {
        dataset.name: output_directory / f"{dataset.name}.{extension}"
        for dataset in model.datasets
    }
    existing = tuple(path for path in paths.values() if path.exists())
    if existing:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Operational output already exists: {names}")
    output_directory.mkdir(parents=True, exist_ok=True)
    return paths


class BufferedDatasetRouter:
    """Validate, order, and batch records using the logical ODM."""

    def __init__(
        self,
        model: OperationalDataModel,
        batch_size: int,
        flush_rows: FlushRows,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._model = model
        self._batch_size = batch_size
        self._flush_rows = flush_rows
        self._buffers: dict[str, list[OrderedRow]] = {
            dataset.name: [] for dataset in model.datasets
        }

    def consume(self, records: Iterable[OperationalRecord]) -> None:
        """Synchronously consume records so callers may safely evict their source."""
        for record in records:
            dataset = self._model.require_dataset(record.dataset)
            column_names = tuple(column.name for column in dataset.columns)
            if set(record.values) != set(column_names):
                raise ValueError(
                    f"Operational record columns do not match ODM: {record.dataset}"
                )
            buffer = self._buffers[dataset.name]
            buffer.append(tuple(record.values[name] for name in column_names))
            if len(buffer) >= self._batch_size:
                self._flush(dataset)

    def flush_all(self) -> None:
        """Flush every non-empty dataset buffer in ODM order."""
        for dataset in self._model.datasets:
            self._flush(dataset)

    def _flush(self, dataset: DatasetDefinition) -> None:
        buffer = self._buffers[dataset.name]
        if not buffer:
            return
        rows = tuple(buffer)
        self._flush_rows(dataset, rows)
        buffer.clear()
