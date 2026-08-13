"""Operational replenishment lifecycle mapping tests."""

from datetime import datetime

from dataforge.core.state.simulation_state import SimulationState
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentStatus,
)
from dataforge.export.operational import OperationalDataBuilder

NOW = datetime(2024, 1, 2, 12)


def replenishment(identifier: str, status: ReplenishmentStatus) -> PendingReplenishment:
    completed = status is ReplenishmentStatus.COMPLETED
    return PendingReplenishment(
        identifier,
        "inventory",
        "location",
        "product",
        10,
        1,
        2,
        datetime(2024, 1, 1),
        status,
        completed_tick_index=3 if completed else None,
        completed_at=NOW if completed else None,
        received_quantity=7 if completed else None,
    )


def test_final_rows_preserve_pending_and_completed_replenishment_facts() -> None:
    state = SimulationState()
    state.create_collection("inventory")
    values = state.create_collection("pending_replenishments")
    values.add("pending", replenishment("pending", ReplenishmentStatus.PENDING))
    values.add("completed", replenishment("completed", ReplenishmentStatus.COMPLETED))

    rows = tuple(
        row
        for row in OperationalDataBuilder().iter_final_rows(state)
        if row.dataset == "replenishments"
    )
    mapped = {str(row.values["replenishment_id"]): row.values for row in rows}
    assert mapped["pending"]["completed_tick_index"] is None
    assert mapped["pending"]["completed_at"] is None
    assert mapped["pending"]["received_quantity"] is None
    assert mapped["completed"]["completed_tick_index"] == 3
    assert mapped["completed"]["completed_at"] == NOW
    assert mapped["completed"]["received_quantity"] == 7
