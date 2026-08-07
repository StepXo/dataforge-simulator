"""Simulation preview endpoints."""

import logging

from fastapi import APIRouter

from dataforge.core.events.event import DomainEvent
from dataforge.core.events.event_bus import EventBus
from dataforge.core.events.event_store import EventStore
from dataforge.runtime.models import (
    SimulationPreviewConfig,
    SimulationPreviewResponse,
)
from dataforge.runtime.preview_service import SimulationPreviewService

router = APIRouter(prefix="/simulations", tags=["simulations"])
logger = logging.getLogger(__name__)
log_handler = logging.StreamHandler()
log_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)
logger.propagate = False
event_store = EventStore()
event_bus = EventBus(event_store)


def log_entity_created(event: DomainEvent) -> None:
    """Log the identifier of a newly generated entity."""
    logger.info("EntityCreated: %s", event.payload["entity_id"])


event_bus.subscribe("EntityCreated", log_entity_created)
preview_service = SimulationPreviewService(event_bus)


@router.post("/preview", response_model=SimulationPreviewResponse)
def create_simulation_preview(
    config: SimulationPreviewConfig,
) -> SimulationPreviewResponse:
    """Generate a deterministic preview without persisting it."""
    return preview_service.generate(config)
