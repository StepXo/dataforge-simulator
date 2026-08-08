"""Tests for shared public export configuration and bounded fan-out."""

from collections.abc import Iterable
from pathlib import Path

import pytest

from dataforge.export.files.configuration import (
    CompositeOperationalDataSink,
    ExportFormat,
    build_export_sink,
)
from dataforge.export.operational.sink import OperationalRecord


class RecordingSink:
    def __init__(self, *, fail_tick: bool = False) -> None:
        self.phases: list[tuple[str, tuple[OperationalRecord, ...]]] = []
        self.fail_tick = fail_tick
        self.closed = False

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self.phases.append(("master", tuple(records)))

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        if self.fail_tick:
            raise OSError("sink failed")
        self.phases.append((f"tick-{tick_index}", tuple(records)))

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self.phases.append(("final", tuple(records)))

    def close(self) -> None:
        self.closed = True


def test_composite_fans_out_one_bounded_phase() -> None:
    first = RecordingSink()
    second = RecordingSink()
    sink = CompositeOperationalDataSink((first, second))
    records = (OperationalRecord("dataset", {"id": str(index)}) for index in range(3))

    sink.write_tick(7, records)
    sink.close()

    assert first.phases == second.phases
    assert first.phases[0][0] == "tick-7"
    assert len(first.phases[0][1]) == 3
    assert first.closed and second.closed


def test_composite_propagates_child_failure() -> None:
    first = RecordingSink()
    failing = RecordingSink(fail_tick=True)
    sink = CompositeOperationalDataSink((first, failing))

    with pytest.raises(OSError, match="sink failed"):
        sink.write_tick(0, ())

    assert first.phases == [("tick-0", ())]


@pytest.mark.parametrize("existing_format", [ExportFormat.CSV, ExportFormat.PARQUET])
def test_both_preflights_every_destination_before_creating_outputs(
    tmp_path: Path, existing_format: ExportFormat
) -> None:
    extension = existing_format.value
    existing_directory = tmp_path / extension
    existing_directory.mkdir(parents=True)
    (existing_directory / f"transactions.{extension}").write_text("existing")

    with pytest.raises(FileExistsError):
        build_export_sink(ExportFormat.BOTH, tmp_path)

    other = "parquet" if extension == "csv" else "csv"
    assert not (tmp_path / other).exists()
