"""Tests for ordered bootstrap execution."""

from datetime import date

import pytest

from dataforge.bootstrap.contracts import BootstrapGenerator
from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange


def make_context() -> SimulationContext:
    return SimulationContext(
        seed=42,
        date_range=DateRange(date(2026, 1, 1), date(2026, 1, 3)),
        random_engine=RandomEngine(42),
        event_bus=EventBus(EventStore()),
    )


class RecordingGenerator:
    def __init__(
        self,
        name: str,
        executions: list[tuple[str, SimulationContext]],
    ) -> None:
        self.name = name
        self.executions = executions

    def generate(self, context: SimulationContext) -> None:
        self.executions.append((self.name, context))


def accepts_bootstrap_generator(generator: BootstrapGenerator) -> BootstrapGenerator:
    return generator


def test_bootstrap_runner_executes_generators_once_in_order_with_same_context() -> None:
    executions: list[tuple[str, SimulationContext]] = []
    context = make_context()
    first = accepts_bootstrap_generator(RecordingGenerator("A", executions))
    second = accepts_bootstrap_generator(RecordingGenerator("B", executions))

    summary = BootstrapRunner([first, second]).run(context)

    assert executions == [("A", context), ("B", context)]
    assert all(received.state is context.state for _, received in executions)
    assert summary.generators_executed == 2
    assert summary.collections_created == 0
    assert summary.records_created == 0


def test_bootstrap_generators_collaborate_through_shared_state() -> None:
    class ParentGenerator:
        def generate(self, context: SimulationContext) -> None:
            parents = context.state.create_collection("parents")
            parents.add("parent-1", {"name": "first"})
            parents.add("parent-2", {"name": "second"})

    class ChildGenerator:
        def generate(self, context: SimulationContext) -> None:
            parents = context.state.collection("parents")
            assert parents.count() == 2
            children = context.state.create_collection("children")
            for index in range(4):
                children.add(f"child-{index}", {"parent_count": parents.count()})

    context = make_context()

    summary = BootstrapRunner([ParentGenerator(), ChildGenerator()]).run(context)

    assert context.state.collection_names() == ("parents", "children")
    assert context.state.total_records == 6
    assert summary.generators_executed == 2
    assert summary.collections_created == 2
    assert summary.records_created == 6


def test_bootstrap_runner_with_no_generators_does_not_modify_state() -> None:
    context = make_context()

    summary = BootstrapRunner([]).run(context)

    assert summary.generators_executed == 0
    assert summary.collections_created == 0
    assert summary.records_created == 0
    assert context.state.collection_names() == ()


def test_bootstrap_runner_propagates_error_without_rollback() -> None:
    calls: list[str] = []
    error = RuntimeError("bootstrap failed")

    class FirstGenerator:
        def generate(self, context: SimulationContext) -> None:
            calls.append("A")
            context.state.create_collection("preserved").add("record", object())

    class FailingGenerator:
        def generate(self, context: SimulationContext) -> None:
            calls.append("B")
            raise error

    class FinalGenerator:
        def generate(self, context: SimulationContext) -> None:
            calls.append("C")

    context = make_context()

    with pytest.raises(RuntimeError) as raised:
        BootstrapRunner([FirstGenerator(), FailingGenerator(), FinalGenerator()]).run(
            context
        )

    assert raised.value is error
    assert calls == ["A", "B"]
    assert context.state.collection("preserved").count() == 1


def test_bootstrap_runner_can_be_invoked_again_manually() -> None:
    calls = 0

    class CountingGenerator:
        def generate(self, context: SimulationContext) -> None:
            nonlocal calls
            calls += 1

    runner = BootstrapRunner([CountingGenerator()])
    context = make_context()

    first_summary = runner.run(context)
    second_summary = runner.run(context)

    assert calls == 2
    assert first_summary.generators_executed == 1
    assert second_summary.generators_executed == 1
