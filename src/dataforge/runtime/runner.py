"""Explicit composition root for the standard MVP simulation pipeline."""

from pathlib import Path

from dataforge.bootstrap.runner import BootstrapRunner
from dataforge.config.geography.loader import load_geography
from dataforge.config.products.loader import load_product_catalog
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.state.simulation_state import SimulationState
from dataforge.core.value_objects import DateRange, TimeRange
from dataforge.engines.customer_behavior.engine import CustomerBehaviorEngine
from dataforge.engines.demand.engine import DemandEngine
from dataforge.engines.inventory.engine import InventoryEngine
from dataforge.engines.metrics.engine import MetricsEngine
from dataforge.engines.pricing.engine import PricingEngine
from dataforge.engines.promotion.engine import PromotionEngine
from dataforge.engines.replenishment.engine import ReplenishmentEngine
from dataforge.engines.time.engine import TimeEngine
from dataforge.engines.transaction.engine import TransactionEngine
from dataforge.engines.validation.engine import StateValidationEngine
from dataforge.generators.customers.generator import CustomerGenerator
from dataforge.generators.geography.generator import GeographyGenerator
from dataforge.generators.inventory.generator import InventoryBootstrapGenerator
from dataforge.generators.products.generator import ProductGenerator
from dataforge.generators.promotions.generator import PromotionBootstrapGenerator
from dataforge.runtime.orchestrator import SimulationOrchestrator
from dataforge.runtime.result import SimulationResult
from dataforge.runtime.summary import aggregate_run_metrics
from dataforge.scenario.loader import load_scenario
from dataforge.scenario.models import ScenarioDefinition


class SimulationRunner:
    """Build and execute a fresh standard runtime for one scenario."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario

    @classmethod
    def from_file(cls, path: Path) -> "SimulationRunner":
        """Create a runner from the existing scenario YAML loader."""
        return cls(load_scenario(path))

    def run(self) -> SimulationResult:
        """Bootstrap and execute one independent in-memory simulation."""
        geography = load_geography(self._scenario.geography.source)
        catalog = load_product_catalog(self._scenario.products.source)

        simulation = self._scenario.simulation
        state = SimulationState()
        random_engine = RandomEngine(simulation.seed)
        event_store = EventStore()
        event_bus = EventBus(event_store)
        context = SimulationContext(
            seed=simulation.seed,
            date_range=DateRange(
                simulation.start_datetime.date(), simulation.end_datetime.date()
            ),
            random_engine=random_engine,
            event_bus=event_bus,
            state=state,
        )

        bootstrap = BootstrapRunner(
            [
                GeographyGenerator(geography, self._scenario.locations),
                ProductGenerator(catalog),
                CustomerGenerator(self._scenario.customers),
                InventoryBootstrapGenerator(self._scenario.inventory),
                PromotionBootstrapGenerator(self._scenario.promotions),
            ]
        )
        bootstrap_summary = bootstrap.run(context)

        clock = SimulationClock(
            TimeRange(simulation.start_datetime, simulation.end_datetime),
            simulation.tick_unit,
        )
        orchestrator = SimulationOrchestrator(
            [
                TimeEngine(),
                PromotionEngine(),
                DemandEngine(self._scenario.demand),
                CustomerBehaviorEngine(),
                PricingEngine(),
                TransactionEngine(),
                InventoryEngine(),
                ReplenishmentEngine(self._scenario.replenishment),
                MetricsEngine(),
                StateValidationEngine(),
            ]
        )
        simulation_summary = orchestrator.run(context, clock)
        metrics_summary = aggregate_run_metrics(
            state, simulation_summary.ticks_processed
        )
        return SimulationResult(
            scenario=self._scenario,
            bootstrap_summary=bootstrap_summary,
            simulation_summary=simulation_summary,
            metrics_summary=metrics_summary,
            state=state,
        )
