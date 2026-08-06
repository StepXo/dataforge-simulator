"""Application service for deterministic simulation previews."""

from dataforge.core.random_engine import RandomEngine
from dataforge.events.event import EntityCreated
from dataforge.events.event_bus import EventBus
from dataforge.simulation.models import (
    SimulatedEntity,
    SimulationPeriod,
    SimulationPreviewConfig,
    SimulationPreviewResponse,
)


class SimulationPreviewService:
    """Generate generic entities from a validated preview configuration."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def generate(self, config: SimulationPreviewConfig) -> SimulationPreviewResponse:
        """Build a reproducible preview for the supplied configuration."""
        random_engine = RandomEngine(config.seed)
        entities: list[SimulatedEntity] = []
        for index in range(1, config.entity_count + 1):
            entity = SimulatedEntity(
                id=f"entity-{index:03d}",
                activity_factor=round(random_engine.uniform(0.50, 1.50), 2),
            )
            entities.append(entity)
            self._event_bus.publish(
                EntityCreated(
                    entity_id=entity.id,
                    activity_factor=entity.activity_factor,
                )
            )
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
