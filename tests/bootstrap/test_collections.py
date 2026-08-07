"""Characterization tests for bootstrap collection preparation."""

import pytest

from dataforge.bootstrap.collections import prepare_empty_collections
from dataforge.state.simulation_state import SimulationState


def test_prepare_empty_collections_creates_missing_and_reuses_empty() -> None:
    state = SimulationState()
    existing = state.create_collection("existing")
    prepare_empty_collections(state, ("existing", "missing"))
    assert state.collection("existing") is existing
    assert state.collection_names() == ("existing", "missing")


def test_prepare_empty_collections_prevalidates_before_creating() -> None:
    state = SimulationState()
    state.create_collection("occupied").add("record", object())
    with pytest.raises(ValueError, match="State collection must be empty: occupied"):
        prepare_empty_collections(state, ("new", "occupied"))
    assert state.has_collection("new") is False
