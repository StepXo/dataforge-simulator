"""Result returned by a complete in-memory simulation run."""

from dataclasses import dataclass

from dataforge.bootstrap.models import BootstrapRunSummary
from dataforge.scenario.models import ScenarioDefinition
from dataforge.simulation.orchestrator import SimulationRunSummary
from dataforge.state.simulation_state import SimulationState


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Expose the real summaries and final state of one simulation execution."""

    scenario: ScenarioDefinition
    bootstrap_summary: BootstrapRunSummary
    simulation_summary: SimulationRunSummary
    state: SimulationState
