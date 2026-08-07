"""Results returned by a complete in-memory simulation run."""

from dataclasses import dataclass
from decimal import Decimal

from dataforge.bootstrap.models import BootstrapRunSummary
from dataforge.core.state.simulation_state import SimulationState
from dataforge.runtime.orchestrator import SimulationRunSummary
from dataforge.scenario.models import ScenarioDefinition


@dataclass(frozen=True, slots=True)
class RunMetricsSummary:
    """Aggregate the official per-tick MetricsContext snapshots for one run."""

    ticks_aggregated: int
    demand_records: int
    demand_units: int
    purchase_intents: int
    intent_units: int
    unassigned_demand_units: int
    price_quotes: int
    total_transactions: int
    completed_transactions: int
    partially_completed_transactions: int
    rejected_transactions: int
    transaction_lines: int
    completed_lines: int
    rejected_lines: int
    completed_units: int
    rejected_units: int
    gross_sales_amount: Decimal
    discount_amount: Decimal
    net_sales_amount: Decimal
    lost_sales_amount: Decimal
    inventory_movements: int
    units_removed_from_inventory: int
    reorder_signals: int
    out_of_stock_signals: int
    replenishments_scheduled: int
    replenishments_completed: int
    units_replenished: int


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Expose the real summaries and final state of one simulation execution."""

    scenario: ScenarioDefinition
    bootstrap_summary: BootstrapRunSummary
    simulation_summary: SimulationRunSummary
    metrics_summary: RunMetricsSummary
    state: SimulationState
