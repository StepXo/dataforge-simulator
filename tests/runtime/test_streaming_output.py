"""Incremental runtime output and retention integration tests."""

from collections.abc import Iterable
from pathlib import Path

import pytest

from dataforge.core.state.simulation_state import SimulationState
from dataforge.export.operational.builder import OperationalDataBuilder
from dataforge.export.operational.sink import OperationalRecord
from dataforge.runtime.runner import SimulationRunner
from dataforge.scenario.loader import load_scenario
from tests.runtime.test_simulation_runner import (
    MASTER_COLLECTIONS,
    TICK_COLLECTIONS,
    scenario_file,
)


class CollectingOperationalDataSink:
    def __init__(self) -> None:
        self.master: list[OperationalRecord] = []
        self.ticks: list[tuple[int, tuple[OperationalRecord, ...]]] = []
        self.final: list[OperationalRecord] = []
        self.closed = False

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self.master.extend(records)

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        self.ticks.append((tick_index, tuple(records)))

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self.final.extend(records)

    def close(self) -> None:
        self.closed = True


def test_streaming_matches_full_history_and_evicts_tick_contexts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = scenario_file(tmp_path)
    full = SimulationRunner.from_file(path).run()
    max_per_collection = 0
    original_evict = SimulationState.evict_tick

    def observe_then_evict(
        state: SimulationState, tick_index: int, collection_names: tuple[str, ...]
    ) -> None:
        nonlocal max_per_collection
        max_per_collection = max(
            max_per_collection,
            *(state.collection(name).count() for name in collection_names),
        )
        original_evict(state, tick_index, collection_names)

    monkeypatch.setattr(SimulationState, "evict_tick", observe_then_evict)
    sink = CollectingOperationalDataSink()
    streamed = SimulationRunner.from_file(path, sink=sink).run()

    assert streamed.metrics_summary == full.metrics_summary
    assert streamed.simulation_summary == full.simulation_summary
    assert sink.closed
    assert max_per_collection == 1
    assert [index for index, _ in sink.ticks] == [0, 1]
    assert all(
        streamed.state.collection(name).count() == 0 for name in TICK_COLLECTIONS
    )
    for name in MASTER_COLLECTIONS:
        assert (
            streamed.state.collection(name).all() == full.state.collection(name).all()
        )

    captured = (
        sink.master + [row for _, rows in sink.ticks for row in rows] + sink.final
    )
    assert captured == list(OperationalDataBuilder().iter_result_rows(full))
    assert sum(row.dataset == "metrics" for row in captured) == 2
    transaction_ids = [
        row.values["transaction_id"]
        for row in captured
        if row.dataset == "transactions"
    ]
    assert len(transaction_ids) == len(set(transaction_ids))


def test_sink_failure_propagates(tmp_path: Path) -> None:
    class FailingSink(CollectingOperationalDataSink):
        def write_tick(
            self, tick_index: int, records: Iterable[OperationalRecord]
        ) -> None:
            raise OSError("output failed")

    with pytest.raises(OSError, match="output failed"):
        SimulationRunner.from_file(scenario_file(tmp_path), sink=FailingSink()).run()


def test_streaming_prefix_is_independent_of_horizon(tmp_path: Path) -> None:
    path = scenario_file(tmp_path)
    short_scenario = load_scenario(path)
    long_scenario = short_scenario.model_copy(
        update={
            "simulation": short_scenario.simulation.model_copy(
                update={
                    "end_datetime": short_scenario.simulation.end_datetime.replace(
                        hour=10
                    )
                }
            )
        }
    )
    short_sink = CollectingOperationalDataSink()
    long_sink = CollectingOperationalDataSink()

    SimulationRunner(short_scenario, sink=short_sink).run()
    SimulationRunner(long_scenario, sink=long_sink).run()

    assert long_sink.ticks[: len(short_sink.ticks)] == short_sink.ticks
