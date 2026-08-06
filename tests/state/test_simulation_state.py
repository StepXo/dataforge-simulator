"""Tests for shared simulation state."""

import pytest

from dataforge.state.simulation_state import SimulationState


def test_simulation_state_starts_without_collections() -> None:
    state = SimulationState()

    assert state.collection_names() == ()
    assert state.total_records == 0
    assert state.has_collection("anything") is False


def test_simulation_state_creates_recovers_and_detects_collection() -> None:
    state = SimulationState()

    created = state.create_collection("records")

    assert state.has_collection("records") is True
    assert state.collection("records") is created


def test_simulation_state_rejects_invalid_or_duplicate_names() -> None:
    state = SimulationState()
    state.create_collection("records")

    with pytest.raises(ValueError, match="already exists"):
        state.create_collection("records")
    with pytest.raises(ValueError, match="non-empty"):
        state.create_collection("")
    with pytest.raises(ValueError, match="outer spaces"):
        state.create_collection(" records ")


def test_simulation_state_missing_collection_raises() -> None:
    with pytest.raises(KeyError):
        SimulationState().collection("missing")


def test_simulation_state_preserves_creation_order_and_counts_mixed_records() -> None:
    state = SimulationState()
    numbers = state.create_collection("numbers")
    labels = state.create_collection("labels")
    numbers.add("one", 1)
    numbers.add("two", 2)
    labels.add("first", "alpha")

    assert state.collection_names() == ("numbers", "labels")
    assert state.total_records == 3
    assert numbers.all() == (1, 2)
    assert labels.all() == ("alpha",)


def test_simulation_state_names_are_a_safe_snapshot() -> None:
    state = SimulationState()
    state.create_collection("records")

    names = state.collection_names()

    assert names + ("external",) != state.collection_names()
    assert state.collection_names() == ("records",)


def test_simulation_state_clear_removes_collections_and_their_contents() -> None:
    state = SimulationState()
    collection = state.create_collection("records")
    collection.add("record", object())

    state.clear()

    assert state.collection_names() == ()
    assert state.total_records == 0
    assert collection.count() == 0
