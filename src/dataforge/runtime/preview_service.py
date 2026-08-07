"""Application service for deterministic simulation previews."""

from dataforge.core.events.event import EntityCreated
from dataforge.core.events.event_bus import EventBus
from dataforge.core.random_engine import RandomEngine
from dataforge.core.simulation_context import SimulationContext
from dataforge.core.value_objects import DateRange
from dataforge.runtime.models import (
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
        context = SimulationContext(
            seed=config.seed,
            date_range=DateRange(
                start_date=config.start_date,
                end_date=config.end_date,
            ),
            random_engine=RandomEngine(config.seed),
            event_bus=self._event_bus,
        )
        entities: list[SimulatedEntity] = []
        for index in range(1, config.entity_count + 1):
            entity = SimulatedEntity(
                id=f"entity-{index:03d}",
                activity_factor=round(
                    context.random_engine.uniform(0.50, 1.50),
                    2,
                ),
            )
            entities.append(entity)
            context.event_bus.publish(
                EntityCreated(
                    entity_id=entity.id,
                    activity_factor=entity.activity_factor,
                )
            )
        period = SimulationPeriod(
            start_date=context.date_range.start_date,
            end_date=context.date_range.end_date,
            days=context.date_range.days,
        )

        return SimulationPreviewResponse(
            simulation_id=f"preview-{context.seed}",
            seed=context.seed,
            period=period,
            entities=entities,
        )
