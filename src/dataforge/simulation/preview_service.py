"""Application service for deterministic simulation previews."""

from dataforge.core.random_engine import RandomEngine
from dataforge.simulation.models import (
    SimulatedEntity,
    SimulationPeriod,
    SimulationPreviewConfig,
    SimulationPreviewResponse,
)


class SimulationPreviewService:
    """Generate generic entities from a validated preview configuration."""

    def generate(self, config: SimulationPreviewConfig) -> SimulationPreviewResponse:
        """Build a reproducible preview for the supplied configuration."""
        random_engine = RandomEngine(config.seed)
        entities = [
            SimulatedEntity(
                id=f"entity-{index:03d}",
                activity_factor=round(random_engine.uniform(0.50, 1.50), 2),
            )
            for index in range(1, config.entity_count + 1)
        ]
        period = SimulationPeriod(
            start_date=config.start_date,
            end_date=config.end_date,
            days=(config.end_date - config.start_date).days + 1,
        )

        return SimulationPreviewResponse(
            simulation_id=f"preview-{config.seed}",
            seed=config.seed,
            period=period,
            entities=entities,
        )
