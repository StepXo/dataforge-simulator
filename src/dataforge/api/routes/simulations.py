"""Simulation preview endpoints."""

from fastapi import APIRouter

from dataforge.simulation.models import (
    SimulationPreviewConfig,
    SimulationPreviewResponse,
)
from dataforge.simulation.preview_service import SimulationPreviewService

router = APIRouter(prefix="/simulations", tags=["simulations"])
preview_service = SimulationPreviewService()


@router.post("/preview", response_model=SimulationPreviewResponse)
def create_simulation_preview(
    config: SimulationPreviewConfig,
) -> SimulationPreviewResponse:
    """Generate a deterministic preview without persisting it."""
    return preview_service.generate(config)
