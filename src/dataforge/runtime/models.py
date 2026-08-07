"""Input and output models for simulation previews."""

from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator


class SimulationPreviewConfig(BaseModel):
    """Validated configuration for a simulation preview."""

    seed: int = Field(ge=0, le=4_294_967_295)
    start_date: date
    end_date: date
    entity_count: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Require the end of the period to be on or after its start."""
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class SimulationPeriod(BaseModel):
    """Inclusive date range represented in a preview."""

    start_date: date
    end_date: date
    days: int


class SimulatedEntity(BaseModel):
    """Generic entity generated for a preview."""

    id: str
    activity_factor: float


class SimulationPreviewResponse(BaseModel):
    """Complete deterministic simulation preview."""

    simulation_id: str
    seed: int
    period: SimulationPeriod
    entities: list[SimulatedEntity]
