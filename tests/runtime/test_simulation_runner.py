"""Integration tests for the standard simulation composition root."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import yaml

from dataforge.runtime import SimulationResult, SimulationRunner
from dataforge.scenario import load_scenario

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


def scenario_file(tmp_path: Path, seed: int = 42) -> Path:
    geography = tmp_path / "arbitrary/geos/foo.yaml"
    products = tmp_path / "unrelated/catalogs/bar.yaml"
    geography.parent.mkdir(parents=True)
    products.parent.mkdir(parents=True)
    geography.write_text(
        yaml.safe_dump(
            {
                "country": {"code": "ZZ", "name": "Fixture"},
                "regions": [{"id": "central", "name": "Central"}],
                "administrative_areas": [
                    {
                        "id": "zone",
                        "name": "Zone",
                        "type": "district",
                        "region_id": "central",
                    }
                ],
                "cities": [
                    {
                        "id": "place",
                        "name": "Place",
                        "administrative_area_id": "zone",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    products.write_text(
        yaml.safe_dump(
            {
                "currency": "USD",
                "categories": [{"id": "category", "name": "Category"}],
                "products": [
                    {
                        "id": "product",
                        "name": "Product",
                        "category_id": "category",
                        "base_price": "10.00",
                        "base_cost": "4.00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / "scenarios/runtime.yaml"
    path.parent.mkdir()
    path.write_text(
        yaml.safe_dump(
            {
                "simulation": {
                    "seed": seed,
                    "start_datetime": "2026-08-10T08:00:00",
                    "end_datetime": "2026-08-10T09:00:00",
                    "tick_unit": "hour",
                },
                "geography": {"source": "../arbitrary/geos/foo.yaml"},
                "products": {"source": "../unrelated/catalogs/bar.yaml"},
                "locations": {"min_per_region": 1, "max_per_region": 1},
                "customers": {"count": 4},
                "inventory": {"product_availability_probability": 1.0},
                "promotions": {"count": 1},
                "demand": {"base_demand_min": 0.1, "base_demand_max": 0.2},
                "replenishment": {
                    "min_lead_time_days": 1,
                    "max_lead_time_days": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def state_snapshot(
    result: SimulationResult,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    return tuple(
        (name, result.state.collection(name).all())
        for name in result.state.collection_names()
    )


def test_runner_executes_bootstrap_and_all_ten_engines(tmp_path: Path) -> None:
    scenario = load_scenario(scenario_file(tmp_path))
    result = SimulationRunner(scenario).run()

    assert isinstance(result, SimulationResult)
    assert result.scenario is scenario
    assert result.bootstrap_summary.generators_executed == 5
    assert result.bootstrap_summary.collections_created == 10
    assert result.simulation_summary.ticks_processed == 2
    assert result.simulation_summary.engine_executions == 20
    assert result.metrics_summary.ticks_aggregated == 2
    assert all(result.state.has_collection(name) for name in MASTER_COLLECTIONS)
    for name in TICK_COLLECTIONS:
        collection = result.state.collection(name)
        assert collection.contains("tick-0")
        assert collection.contains("tick-1")
    try:
        result.__setattr__("state", result.state)
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("SimulationResult must be immutable")


def test_each_run_uses_fresh_reproducible_runtime(tmp_path: Path) -> None:
    runner = SimulationRunner.from_file(scenario_file(tmp_path))

    first = runner.run()
    second = runner.run()

    assert first.state is not second.state
    assert state_snapshot(first) == state_snapshot(second)
    assert first.bootstrap_summary == second.bootstrap_summary
    assert first.simulation_summary == second.simulation_summary


def test_from_file_and_loaded_scenario_are_equivalent(tmp_path: Path) -> None:
    path = scenario_file(tmp_path)

    from_file = SimulationRunner.from_file(path).run()
    from_definition = SimulationRunner(load_scenario(path)).run()

    assert state_snapshot(from_file) == state_snapshot(from_definition)
    assert from_file.bootstrap_summary == from_definition.bootstrap_summary
    assert from_file.simulation_summary == from_definition.simulation_summary


def test_known_different_seeds_change_synthetic_state(tmp_path: Path) -> None:
    first_path = scenario_file(tmp_path / "first", seed=1)
    second_path = scenario_file(tmp_path / "second", seed=2)

    first = SimulationRunner.from_file(first_path).run()
    second = SimulationRunner.from_file(second_path).run()

    synthetic_names = ("locations", "products", "customers", "inventory", "promotions")
    first_values = tuple(first.state.collection(name).all() for name in synthetic_names)
    second_values = tuple(
        second.state.collection(name).all() for name in synthetic_names
    )
    assert first_values != second_values
