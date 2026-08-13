"""Tests for scheduling and completing stock replenishments."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.inventory.models import (
    InventoryContext,
    InventoryMovement,
    InventoryMovementType,
    ReorderSignal,
)
from dataforge.engines.replenishment.engine import (
    ReplenishmentEngine,
    ReplenishmentEngineConfig,
    _days_to_ticks,
)
from dataforge.engines.replenishment.models import (
    PendingReplenishment,
    ReplenishmentContext,
    ReplenishmentStatus,
)
from dataforge.engines.time.models import TemporalContext
from dataforge.generators.inventory.models import InventoryItem

NOW = datetime(2026, 8, 15, 12)


def inventory(stock: int = 8) -> InventoryItem:
    return InventoryItem("inventory-a", "location-a", "product-a", stock, 10, 100, True)


def signal(item: InventoryItem) -> ReorderSignal:
    return ReorderSignal(
        item.id,
        item.location_id,
        item.product_id,
        item.current_stock,
        item.reorder_point,
        item.max_stock,
        0,
    )


def pending(
    *,
    due: int = 0,
    requested: int = 92,
    status: ReplenishmentStatus = ReplenishmentStatus.PENDING,
) -> PendingReplenishment:
    return PendingReplenishment(
        "replenishment-0-000001",
        "inventory-a",
        "location-a",
        "product-a",
        requested,
        -1,
        due,
        NOW - timedelta(hours=1),
        status,
    )


def runtime(
    *,
    tick: int = 0,
    item: InventoryItem | None = None,
    signals: tuple[ReorderSignal, ...] = (),
    pendings: tuple[PendingReplenishment, ...] = (),
    seed: int = 7,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    selected = item or inventory()
    store = EventStore()
    context = SimulationContext(
        seed,
        DateRange(date(2026, 8, 15), date(2026, 8, 20)),
        RandomEngine(seed),
        EventBus(store),
    )
    end = NOW + timedelta(hours=max(tick, 72))
    clock = SimulationClock(TimeRange(NOW, end), TickUnit.HOUR)
    for _ in range(tick):
        clock.advance()
    stock = context.state.create_collection("inventory")
    stock.add(selected.id, selected)
    temporal = context.state.create_collection("temporal_context")
    temporal.add(
        f"tick-{tick}", TemporalContext(tick, clock.current_time, TickUnit.HOUR)
    )
    inventory_context = context.state.create_collection("inventory_context")
    inventory_context.add(
        f"tick-{tick}",
        InventoryContext(tick, clock.current_time, (), signals, (), 0, 0),
    )
    if pendings:
        values = context.state.create_collection("pending_replenishments")
        for value in pendings:
            values.add(value.id, value)
    return context, clock, store


def result(
    *,
    tick: int = 0,
    item: InventoryItem | None = None,
    signals: tuple[ReorderSignal, ...] = (),
    pendings: tuple[PendingReplenishment, ...] = (),
    seed: int = 7,
    config: ReplenishmentEngineConfig | None = None,
) -> tuple[ReplenishmentContext, SimulationContext, EventStore]:
    context, clock, store = runtime(
        tick=tick, item=item, signals=signals, pendings=pendings, seed=seed
    )
    ReplenishmentEngine(config).execute(context, clock)
    value = context.state.collection("replenishment_context").require(f"tick-{tick}")
    assert isinstance(value, ReplenishmentContext)
    return value, context, store


def test_config_and_models_validate_and_are_immutable() -> None:
    with pytest.raises(ValidationError):
        ReplenishmentEngineConfig(min_lead_time_days=0)
    with pytest.raises(ValidationError):
        ReplenishmentEngineConfig(min_lead_time_days=3, max_lead_time_days=2)
    value = pending(due=1)
    with pytest.raises(FrozenInstanceError):
        value.__setattr__("status", ReplenishmentStatus.COMPLETED)


def test_reorder_schedules_reproducible_future_pending() -> None:
    item = inventory(8)
    config = ReplenishmentEngineConfig(min_lead_time_days=1, max_lead_time_days=3)
    first, first_context, store = result(
        item=item, signals=(signal(item),), config=config
    )
    second, _, _ = result(item=item, signals=(signal(item),), config=config)
    scheduled = first.scheduled[0]
    assert first == second
    assert scheduled.id == "replenishment-0-000001"
    assert scheduled.requested_quantity == 92
    assert 24 <= scheduled.due_tick_index <= 72
    assert scheduled.status is ReplenishmentStatus.PENDING
    assert (
        first_context.state.collection("inventory").require(item.id).current_stock == 8
    )
    assert [event.event_type for event in store.all_events()] == [
        "ReplenishmentScheduled",
        "ReplenishmentContextGenerated",
    ]


def test_existing_pending_prevents_duplicate_schedule() -> None:
    item = inventory(8)
    existing = pending(due=2)
    value, context, _ = result(item=item, signals=(signal(item),), pendings=(existing,))
    assert value.scheduled == ()
    assert context.state.collection("pending_replenishments").count() == 1


@pytest.mark.parametrize("stock,received", [(8, 92), (20, 80), (100, 0)])
def test_due_replenishment_uses_current_stock_and_never_exceeds_max(
    stock: int, received: int
) -> None:
    item = inventory(stock)
    value, context, store = result(tick=1, item=item, pendings=(pending(due=1),))
    updated = context.state.collection("inventory").require(item.id)
    assert updated.current_stock == 100
    assert value.units_received == received
    assert len(value.movements) == (1 if received else 0)
    if received:
        movement = value.movements[0]
        assert movement.movement_type is InventoryMovementType.REPLENISHMENT
        assert movement.transaction_id is None and movement.basket_id is None
        assert movement.quantity == received
        assert movement.replenishment_id == "replenishment-0-000001"
        tick_start = NOW + timedelta(hours=1)
        assert tick_start <= movement.occurred_at < tick_start + timedelta(hours=1)
    completed = context.state.collection("pending_replenishments").require(
        "replenishment-0-000001"
    )
    assert completed.status is ReplenishmentStatus.COMPLETED
    assert completed.completed_tick_index == 1
    assert completed.completed_at is not None
    assert completed.received_quantity == received
    if received:
        matching = tuple(
            movement
            for movement in value.movements
            if movement.replenishment_id == completed.id
        )
        assert len(matching) == 1
        assert matching[0].quantity == completed.received_quantity
        assert matching[0].occurred_at == completed.completed_at
    types = [event.event_type for event in store.all_events()]
    assert types[-2:] == ["ReplenishmentCompleted", "ReplenishmentContextGenerated"]


def test_replenishment_movement_sequence_continues_after_sale_movements() -> None:
    item = inventory(8)
    context, clock, _ = runtime(tick=1, item=item, pendings=(pending(due=1),))
    sale = InventoryMovement(
        "inventory-movement-1-000001",
        item.id,
        item.location_id,
        item.product_id,
        "transaction-1-000001",
        "basket-1-000001",
        InventoryMovementType.SALE,
        1,
        9,
        8,
        1,
        NOW + timedelta(hours=1, minutes=1),
    )
    context.state.collection("inventory_context").replace(
        "tick-1",
        InventoryContext(1, clock.current_time, (sale,), (), (), 1, 1),
    )

    ReplenishmentEngine().execute(context, clock)

    result = context.state.collection("replenishment_context").require("tick-1")
    assert isinstance(result, ReplenishmentContext)
    assert [movement.id for movement in result.movements] == [
        "inventory-movement-1-000002"
    ]


def test_completion_happens_before_old_signal_and_does_not_reschedule() -> None:
    item = inventory(8)
    value, context, _ = result(
        tick=1,
        item=item,
        signals=(signal(item),),
        pendings=(pending(due=1),),
    )
    assert value.replenishments_completed == 1
    assert value.replenishments_scheduled == 0
    assert context.state.collection("pending_replenishments").count() == 1


def test_pending_persists_until_due_tick() -> None:
    item = inventory(8)
    context, clock, _ = runtime(signals=(signal(item),))
    engine = ReplenishmentEngine(
        ReplenishmentEngineConfig(min_lead_time_days=2, max_lead_time_days=2)
    )
    engine.execute(context, clock)
    assert context.state.collection("inventory").require(item.id).current_stock == 8
    clock.advance()
    context.state.collection("temporal_context").add(
        "tick-1", TemporalContext(1, clock.current_time, TickUnit.HOUR)
    )
    context.state.collection("inventory_context").add(
        "tick-1", InventoryContext(1, clock.current_time, (), (), (), 0, 0)
    )
    engine.execute(context, clock)
    assert context.state.collection("inventory").require(item.id).current_stock == 8
    for _ in range(47):
        clock.advance()
    context.state.collection("temporal_context").add(
        "tick-48", TemporalContext(48, clock.current_time, TickUnit.HOUR)
    )
    context.state.collection("inventory_context").add(
        "tick-48", InventoryContext(48, clock.current_time, (), (), (), 0, 0)
    )
    engine.execute(context, clock)
    assert context.state.collection("inventory").require(item.id).current_stock == 100
    assert (
        context.state.collection("replenishment_context").require("tick-1").completed
        == ()
    )
    assert (
        len(
            context.state.collection("replenishment_context")
            .require("tick-48")
            .completed
        )
        == 1
    )


def test_empty_context_and_duplicate_execution() -> None:
    context, clock, store = runtime()
    engine = ReplenishmentEngine()
    engine.execute(context, clock)
    value = context.state.collection("replenishment_context").require("tick-0")
    assert value == ReplenishmentContext(0, NOW, (), (), (), 0, 0, 0)
    before = store.count()
    with pytest.raises(ValueError, match="already executed"):
        engine.execute(context, clock)
    assert store.count() == before
    assert (
        context.state.collection("inventory").require("inventory-a").current_stock == 8
    )


def test_invalid_due_inventory_fails_before_mutation() -> None:
    item = InventoryItem("inventory-a", "location-a", "product-a", 8, 10, 100, False)
    context, clock, store = runtime(tick=1, item=item, pendings=(pending(due=1),))
    with pytest.raises(ValueError, match="Invalid due"):
        ReplenishmentEngine().execute(context, clock)
    assert context.state.collection("inventory").require(item.id).current_stock == 8
    assert store.count() == 0


def test_lead_time_days_convert_to_hourly_and_daily_ticks() -> None:
    hourly = SimulationClock(TimeRange(NOW, NOW + timedelta(days=4)), TickUnit.HOUR)
    daily = SimulationClock(TimeRange(NOW, NOW + timedelta(days=4)), TickUnit.DAY)
    assert _days_to_ticks(1, hourly) == 24
    assert _days_to_ticks(3, hourly) == 72
    assert _days_to_ticks(1, daily) == 1
    assert _days_to_ticks(3, daily) == 3
