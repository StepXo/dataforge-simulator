"""Tests for temporal promotion activation."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

from dataforge.core.engine import SimulationEngine
from dataforge.core.events.event import DomainEvent
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.tick import TickUnit
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.promotion.engine import PromotionEngine, annual_occurrence
from dataforge.engines.promotion.events import PromotionContextGenerated
from dataforge.engines.promotion.models import ActivePromotion, PromotionContext
from dataforge.engines.time.engine import TimeEngine
from dataforge.generators.promotions.models import (
    Promotion,
    PromotionChannel,
    PromotionTargetType,
)


def promotion(
    identifier: str = "promotion-a",
    start: date = date(2026, 8, 10),
    end: date = date(2026, 8, 12),
    active: bool = True,
) -> Promotion:
    return Promotion(
        identifier,
        identifier,
        start,
        end,
        PromotionTargetType.CATEGORY,
        ("tacos",),
        PromotionChannel.MOBILE,
        0.15,
        0.30,
        active,
    )


def runtime(
    start: datetime,
    end: datetime | None = None,
    tick_unit: TickUnit = TickUnit.DAY,
) -> tuple[SimulationContext, SimulationClock, EventStore]:
    event_store = EventStore()
    end = end or start
    context = SimulationContext(
        42,
        DateRange(start.date(), end.date()),
        RandomEngine(42),
        EventBus(event_store),
    )
    clock = SimulationClock(TimeRange(start, end), tick_unit)
    return context, clock, event_store


def add_promotions(context: SimulationContext, *values: Promotion) -> None:
    collection = context.state.create_collection("promotions")
    for value in values:
        collection.add(value.id, value)


def execute_tick(
    current_time: datetime,
    *values: Promotion,
) -> PromotionContext:
    context, clock, _ = runtime(current_time)
    add_promotions(context, *values)
    TimeEngine().execute(context, clock)
    PromotionEngine().execute(context, clock)
    result = context.state.collection("promotion_context").require("tick-0")
    assert isinstance(result, PromotionContext)
    return result


def test_active_promotion_and_context_are_immutable() -> None:
    active = ActivePromotion(
        "promotion-a",
        PromotionTargetType.PRODUCT,
        ("product-a",),
        PromotionChannel.MOBILE,
        0.1,
        0.2,
    )
    context = PromotionContext(3, datetime(2026, 8, 10, 12), (active,))
    empty = PromotionContext(4, datetime(2026, 8, 11), ())
    assert active.target_ids == ("product-a",)
    assert context.active_promotions == (active,)
    assert empty.active_promotions == ()
    with pytest.raises(FrozenInstanceError):
        active.__setattr__("discount_rate", 0.5)
    with pytest.raises(FrozenInstanceError):
        context.__setattr__("tick_index", 5)


@pytest.mark.parametrize(
    "day,expected",
    [
        (9, ()),
        (10, ("promotion-a",)),
        (11, ("promotion-a",)),
        (12, ("promotion-a",)),
        (13, ()),
    ],
)
def test_promotion_date_bounds_are_inclusive(
    day: int, expected: tuple[str, ...]
) -> None:
    result = execute_tick(datetime(2026, 8, day, 12), promotion())
    assert tuple(item.promotion_id for item in result.active_promotions) == expected


def test_multiple_promotions_preserve_order_and_ignore_inactive() -> None:
    result = execute_tick(
        datetime(2026, 8, 11),
        promotion("a"),
        promotion("b", start=date(2026, 8, 12), end=date(2026, 8, 13)),
        promotion("c"),
        promotion("d", active=False),
    )
    assert tuple(item.promotion_id for item in result.active_promotions) == ("a", "c")
    assert result.active_promotions[0].target_type is PromotionTargetType.CATEGORY
    assert result.active_promotions[0].target_ids == ("tacos",)
    assert result.active_promotions[0].channel is PromotionChannel.MOBILE


def test_empty_active_context_is_stored_and_published_before_handler() -> None:
    context, clock, store = runtime(datetime(2026, 8, 9))
    add_promotions(context, promotion())
    TimeEngine().execute(context, clock)
    observed: list[DomainEvent] = []

    def assert_stored(event: DomainEvent) -> None:
        assert context.state.collection("promotion_context").contains("tick-0")
        observed.append(event)

    context.event_bus.subscribe("PromotionContextGenerated", assert_stored)
    PromotionEngine().execute(context, clock)
    result = context.state.collection("promotion_context").require("tick-0")
    assert isinstance(result, PromotionContext)
    assert result.active_promotions == ()
    assert len(observed) == 1
    assert isinstance(observed[0], PromotionContextGenerated)
    assert observed[0].payload == {
        "tick_index": 0,
        "current_time": "2026-08-09T00:00:00",
        "active_promotions": [],
    }
    assert (
        sum(
            event.event_type == "PromotionContextGenerated"
            for event in store.all_events()
        )
        == 1
    )


def test_duplicate_execution_fails_without_second_event() -> None:
    context, clock, store = runtime(datetime(2026, 8, 10))
    add_promotions(context, promotion())
    TimeEngine().execute(context, clock)
    engine = PromotionEngine()
    engine.execute(context, clock)
    before = store.count()
    with pytest.raises(ValueError, match="State key already exists: tick-0"):
        engine.execute(context, clock)
    assert store.count() == before


def test_engine_requires_promotions_and_current_temporal_context() -> None:
    context, clock, _ = runtime(datetime(2026, 8, 10))
    with pytest.raises(ValueError, match="missing: promotions"):
        PromotionEngine().execute(context, clock)
    add_promotions(context, promotion())
    with pytest.raises(ValueError, match="missing: temporal_context"):
        PromotionEngine().execute(context, clock)
    context.state.create_collection("temporal_context")
    with pytest.raises(ValueError, match="missing for tick: 0"):
        PromotionEngine().execute(context, clock)


def test_promotion_engine_satisfies_protocol_and_does_not_advance_clock() -> None:
    engine: SimulationEngine = PromotionEngine()
    context, clock, _ = runtime(datetime(2026, 8, 10))
    add_promotions(context, promotion())
    TimeEngine().execute(context, clock)
    engine.execute(context, clock)
    assert clock.tick_index == 0
    assert clock.current_time == datetime(2026, 8, 10)


def test_annual_occurrence_is_stable_and_recurs_across_years() -> None:
    pattern = promotion("annual", start=date(2000, 4, 5), end=date(2000, 4, 12))
    occurrence_2024 = annual_occurrence(pattern, 2024, 42)
    assert occurrence_2024 == annual_occurrence(pattern, 2024, 42)
    occurrence_2025 = annual_occurrence(pattern, 2025, 42)
    assert occurrence_2024[0].year == 2024
    assert occurrence_2025[0].year == 2025
    assert occurrence_2024[0].month == occurrence_2025[0].month == 4
    assert occurrence_2024[0].day != occurrence_2025[0].day
    assert (occurrence_2024[1] - occurrence_2024[0]).days == 7
    assert (occurrence_2025[1] - occurrence_2025[0]).days == 7


def test_annual_pattern_exists_but_is_inactive_outside_occurrence() -> None:
    pattern = promotion("april", start=date(2000, 4, 5), end=date(2000, 4, 12))
    result = execute_tick(datetime(2024, 1, 2), pattern)
    assert result.active_promotions == ()
