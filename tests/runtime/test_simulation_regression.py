"""Permanent smoke and temporal regression coverage for the complete runtime."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Literal

import pytest

from dataforge.core.simulation_clock import TICK_DELTAS
from dataforge.core.tick import TickUnit
from dataforge.engines.demand.engine import (
    DemandEngineConfig,
    _intraday_factor,
    _time_of_day_factor,
)
from dataforge.engines.time.models import time_of_day_for_hour
from dataforge.engines.validation.models import ValidationContext
from dataforge.generators.inventory.models import InventoryItem
from dataforge.runtime import SimulationResult, SimulationRunner
from dataforge.scenario import load_scenario
from dataforge.scenario.models import ScenarioDefinition

SCENARIO_PATH = Path("configs/scenarios/smoke-test.yaml")
ENGINE_COUNT = 10
MASTER_COLLECTIONS = (
    "countries",
    "regions",
    "administrative_areas",
    "cities",
    "locations",
    "categories",
    "products",
    "customers",
    "inventory",
    "promotions",
)
TICK_COLLECTIONS = (
    "temporal_context",
    "promotion_context",
    "demand_context",
    "customer_behavior_context",
    "pricing_context",
    "transaction_context",
    "inventory_context",
    "replenishment_context",
    "metrics_context",
    "validation_context",
)
Horizon = Literal["day", "month", "six_months"]


@dataclass(frozen=True, slots=True)
class TemporalCase:
    horizon: Horizon
    tick_unit: TickUnit
    seed: int
    start: datetime

    @property
    def id(self) -> str:
        return (
            f"{self.start:%Y-%m-%d}-{self.horizon}-"
            f"{self.tick_unit.value}-seed-{self.seed}"
        )


STARTS = (datetime(2024, 1, 1), datetime(2024, 7, 1))
FAST_HORIZONS: tuple[Horizon, ...] = ("day", "month")
HORIZONS: tuple[Horizon, ...] = ("day", "month", "six_months")
TICK_UNITS = (TickUnit.HOUR, TickUnit.DAY)
SEEDS = (42, 137)
FAST_CASES = tuple(
    TemporalCase(horizon, tick_unit, 42, start)
    for start, horizon, tick_unit in product(
        STARTS,
        FAST_HORIZONS,
        TICK_UNITS,
    )
)
TEMPORAL_CASES = tuple(
    TemporalCase(horizon, tick_unit, seed, start)
    for start, horizon, tick_unit, seed in product(
        STARTS,
        HORIZONS,
        TICK_UNITS,
        SEEDS,
    )
)


def _last_calendar_day(start: datetime, months: int) -> datetime:
    month_index = start.month - 1 + months - 1
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, monthrange(year, month)[1], 23)


def _end_datetime(case: TemporalCase) -> datetime:
    if case.horizon == "day":
        return case.start.replace(hour=23)
    if case.horizon == "month":
        return _last_calendar_day(case.start, 1)
    return _last_calendar_day(case.start, 6)


def _scenario(case: TemporalCase) -> ScenarioDefinition:
    scenario = load_scenario(SCENARIO_PATH)
    simulation = scenario.simulation.model_copy(
        update={
            "seed": case.seed,
            "start_datetime": case.start,
            "end_datetime": _end_datetime(case),
            "tick_unit": case.tick_unit,
        }
    )
    return scenario.model_copy(update={"simulation": simulation})


def _run(case: TemporalCase) -> SimulationResult:
    return SimulationRunner(_scenario(case)).run()


def _expected_ticks(case: TemporalCase) -> int:
    duration = _end_datetime(case) - case.start
    return int(duration / TICK_DELTAS[case.tick_unit]) + 1


def _assert_run_invariants(result: SimulationResult, expected_ticks: int) -> None:
    simulation = result.simulation_summary
    metrics = result.metrics_summary
    assert simulation.ticks_processed == expected_ticks > 0
    assert simulation.engine_executions == expected_ticks * ENGINE_COUNT
    assert metrics.ticks_aggregated == expected_ticks
    assert metrics.demand_units == (
        metrics.completed_units
        + metrics.rejected_units
        + metrics.unassigned_demand_units
    )
    assert metrics.total_transactions == (
        metrics.completed_transactions
        + metrics.partially_completed_transactions
        + metrics.rejected_transactions
    )
    assert metrics.transaction_lines == metrics.completed_lines + metrics.rejected_lines
    numeric_metrics = (
        metrics.demand_units,
        metrics.unassigned_demand_units,
        metrics.total_transactions,
        metrics.completed_transactions,
        metrics.partially_completed_transactions,
        metrics.rejected_transactions,
        metrics.transaction_lines,
        metrics.completed_lines,
        metrics.rejected_lines,
        metrics.completed_units,
        metrics.rejected_units,
    )
    assert all(value >= 0 for value in numeric_metrics)
    assert metrics.net_sales_amount >= 0
    assert metrics.lost_sales_amount >= 0

    inventory = result.state.collection("inventory").all()
    assert inventory
    assert all(
        isinstance(item, InventoryItem) and 0 <= item.current_stock <= item.max_stock
        for item in inventory
    )
    validations = result.state.collection("validation_context")
    assert validations.count() == expected_ticks
    assert all(
        isinstance(item, ValidationContext) and item.valid for item in validations.all()
    )


@pytest.mark.parametrize("case", FAST_CASES, ids=lambda case: case.id)
def test_fast_calendar_matrix_completes_full_pipeline(case: TemporalCase) -> None:
    result = _run(case)

    _assert_run_invariants(result, _expected_ticks(case))
    assert all(result.state.has_collection(name) for name in MASTER_COLLECTIONS)
    assert all(result.state.has_collection(name) for name in TICK_COLLECTIONS)


@pytest.mark.slow
@pytest.mark.parametrize("case", TEMPORAL_CASES, ids=lambda case: case.id)
def test_complete_temporal_regression_matrix(case: TemporalCase) -> None:
    _assert_run_invariants(_run(case), _expected_ticks(case))


def test_smoke_scenario_is_reproducible() -> None:
    runner = SimulationRunner.from_file(SCENARIO_PATH)

    first = runner.run()
    second = runner.run()

    assert first.metrics_summary == second.metrics_summary
    for name in TICK_COLLECTIONS:
        assert first.state.collection(name).all() == second.state.collection(name).all()


def test_known_seeds_change_synthetic_output() -> None:
    first = _run(TemporalCase("day", TickUnit.HOUR, 42, STARTS[0]))
    second = _run(TemporalCase("day", TickUnit.HOUR, 137, STARTS[0]))

    synthetic = ("locations", "products", "customers", "inventory", "promotions")
    assert tuple(first.state.collection(name).all() for name in synthetic) != tuple(
        second.state.collection(name).all() for name in synthetic
    )


def test_hourly_and_daily_ticks_use_same_intraday_profile() -> None:
    config = DemandEngineConfig()

    daily = _intraday_factor(TickUnit.DAY, 0, config)
    hourly_sum = sum(
        _time_of_day_factor(time_of_day_for_hour(hour), config) for hour in range(24)
    )

    assert daily == hourly_sum
    assert _intraday_factor(TickUnit.HOUR, 12, config) == config.lunch_factor


def test_one_day_is_prefix_of_one_month() -> None:
    short = _run(TemporalCase("day", TickUnit.HOUR, 42, STARTS[0]))
    long = _run(TemporalCase("month", TickUnit.HOUR, 42, STARTS[0]))

    for name in TICK_COLLECTIONS:
        assert (
            short.state.collection(name).all() == long.state.collection(name).all()[:24]
        )
    assert (
        short.state.collection("promotions").all()
        == long.state.collection("promotions").all()
    )


def test_one_month_is_prefix_of_six_months_daily() -> None:
    short_case = TemporalCase("month", TickUnit.DAY, 42, STARTS[1])
    long_case = TemporalCase("six_months", TickUnit.DAY, 42, STARTS[1])
    short = _run(short_case)
    long = _run(long_case)
    prefix = _expected_ticks(short_case)

    for name in TICK_COLLECTIONS:
        assert (
            short.state.collection(name).all()
            == long.state.collection(name).all()[:prefix]
        )
    assert (
        short.state.collection("promotions").all()
        == long.state.collection("promotions").all()
    )
