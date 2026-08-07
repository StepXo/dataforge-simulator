"""Horizon invariance and runtime prefix consistency tests."""

from pathlib import Path

import yaml

from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.config.geography.loader import load_geography
from dataforge.config.products.loader import load_product_catalog
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.generators.customers.generator import CustomerGenerator
from dataforge.generators.geography.generator import GeographyGenerator
from dataforge.generators.inventory.generator import InventoryBootstrapGenerator
from dataforge.generators.products.generator import ProductGenerator
from dataforge.generators.promotions.generator import PromotionBootstrapGenerator
from dataforge.runtime import SimulationRunner
from dataforge.scenario import load_scenario
from tests.runtime.test_simulation_runner import scenario_file

MASTER_COLLECTIONS = ("locations", "products", "customers", "inventory", "promotions")
PREFIX_COLLECTIONS = (
    "demand_context",
    "customer_behavior_context",
    "pricing_context",
    "transaction_context",
    "inventory_context",
    "metrics_context",
)


def scenario_with_end(source: Path, target: Path, end: str) -> Path:
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    loaded = load_scenario(source)
    payload["simulation"]["tick_unit"] = "day"
    payload["simulation"]["end_datetime"] = end
    payload["geography"]["source"] = str(loaded.geography.source)
    payload["products"]["source"] = str(loaded.products.source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return target


def bootstrap_snapshot(path: Path) -> tuple[tuple[str, tuple[object, ...]], ...]:
    scenario = load_scenario(path)
    simulation = scenario.simulation
    context = SimulationContext(
        simulation.seed,
        DateRange(simulation.start_datetime.date(), simulation.end_datetime.date()),
        RandomEngine(simulation.seed),
        EventBus(EventStore()),
    )
    BootstrapRunner(
        [
            GeographyGenerator(
                load_geography(scenario.geography.source), scenario.locations
            ),
            ProductGenerator(load_product_catalog(scenario.products.source)),
            CustomerGenerator(scenario.customers),
            InventoryBootstrapGenerator(scenario.inventory),
            PromotionBootstrapGenerator(scenario.promotions),
        ]
    ).run(context)
    return tuple(
        (name, context.state.collection(name).all()) for name in MASTER_COLLECTIONS
    )


def test_bootstrap_and_runtime_prefix_are_horizon_invariant(tmp_path: Path) -> None:
    base = scenario_file(tmp_path / "base")
    short = scenario_with_end(base, tmp_path / "short.yaml", "2026-08-12T08:00:00")
    long = scenario_with_end(base, tmp_path / "long.yaml", "2026-08-20T08:00:00")
    assert bootstrap_snapshot(short) == bootstrap_snapshot(long)

    short_result = SimulationRunner.from_file(short).run()
    long_result = SimulationRunner.from_file(long).run()
    ticks = short_result.simulation_summary.ticks_processed
    for name in PREFIX_COLLECTIONS:
        short_values = short_result.state.collection(name)
        long_values = long_result.state.collection(name)
        for tick in range(ticks):
            assert short_values.require(f"tick-{tick}") == long_values.require(
                f"tick-{tick}"
            )
    assert ticks < long_result.simulation_summary.ticks_processed
