"""Integration tests for TimeEngine followed by PromotionEngine."""

from datetime import date, datetime

import pytest

from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.promotion.engine import PromotionEngine
from dataforge.engines.promotion.models import PromotionContext
from dataforge.engines.time.engine import TimeEngine
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore
from dataforge.promotions.models import Promotion, PromotionChannel, PromotionTargetType
from dataforge.simulation.orchestrator import SimulationOrchestrator


def runtime(start: datetime, end: datetime, tick_unit: TickUnit):
    store = EventStore()
    context = SimulationContext(
        42, DateRange(start.date(), end.date()), RandomEngine(42), EventBus(store)
    )
    clock = SimulationClock(TimeRange(start, end), tick_unit)
    context.state.create_collection("promotions").add(
        "promotion-a",
        Promotion(
            "promotion-a",
            "Promotion A",
            date(2026, 8, 10),
            date(2026, 8, 12),
            PromotionTargetType.GLOBAL,
            (),
            PromotionChannel.ALL,
            0.1,
            0.2,
            True,
        ),
    )
    return context, clock, store


def test_daily_orchestration_preserves_history_and_event_count() -> None:
    context, clock, store = runtime(
        datetime(2026, 8, 9), datetime(2026, 8, 11), TickUnit.DAY
    )
    summary = SimulationOrchestrator([TimeEngine(), PromotionEngine()]).run(
        context, clock
    )
    collection = context.state.collection("promotion_context")
    contexts = [
        value for value in collection.all() if isinstance(value, PromotionContext)
    ]
    assert summary.ticks_processed == 3
    assert summary.engine_executions == 6
    assert tuple(collection.contains(f"tick-{index}") for index in range(3)) == (
        True,
        True,
        True,
    )
    assert [len(item.active_promotions) for item in contexts] == [0, 1, 1]
    assert (
        sum(
            event.event_type == "PromotionContextGenerated"
            for event in store.all_events()
        )
        == 3
    )


def test_hourly_ticks_keep_daily_promotion_active() -> None:
    context, clock, _ = runtime(
        datetime(2026, 8, 10, 8), datetime(2026, 8, 10, 10), TickUnit.HOUR
    )
    SimulationOrchestrator([TimeEngine(), PromotionEngine()]).run(context, clock)
    contexts = [
        value
        for value in context.state.collection("promotion_context").all()
        if isinstance(value, PromotionContext)
    ]
    assert [item.current_time.hour for item in contexts] == [8, 9, 10]
    assert all(len(item.active_promotions) == 1 for item in contexts)


def test_wrong_engine_order_fails_without_advancing_clock() -> None:
    context, clock, _ = runtime(
        datetime(2026, 8, 10), datetime(2026, 8, 12), TickUnit.DAY
    )
    with pytest.raises(ValueError, match="missing: temporal_context"):
        SimulationOrchestrator([PromotionEngine(), TimeEngine()]).run(context, clock)
    assert clock.tick_index == 0
    assert context.state.has_collection("promotion_context") is False
