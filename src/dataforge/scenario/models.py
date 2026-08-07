"""Typed configuration contract for a complete simulation scenario."""

from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from dataforge.core.tick import TickUnit
from dataforge.engines.demand.engine import DemandEngineConfig
from dataforge.engines.replenishment.engine import ReplenishmentEngineConfig
from dataforge.generators.customers.generator import CustomerGenerationConfig
from dataforge.generators.geography.generator import LocationGenerationConfig
from dataforge.generators.inventory.generator import InventoryGenerationConfig
from dataforge.generators.promotions.generator import PromotionGenerationConfig


class SimulationDefinition(BaseModel):
    """Describe the deterministic time range of a scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    start_datetime: datetime
    end_datetime: datetime
    tick_unit: TickUnit

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.end_datetime <= self.start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        return self


class GeographySourceDefinition(BaseModel):
    """Reference an external geography definition without loading it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path


class ProductCatalogSourceDefinition(BaseModel):
    """Reference an external product catalog without loading it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path


class ScenarioDefinition(BaseModel):
    """Describe all configurable inputs of a simulation without executing it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    simulation: SimulationDefinition
    geography: GeographySourceDefinition
    products: ProductCatalogSourceDefinition
    locations: LocationGenerationConfig
    customers: CustomerGenerationConfig
    inventory: InventoryGenerationConfig
    promotions: PromotionGenerationConfig
    demand: DemandEngineConfig
    replenishment: ReplenishmentEngineConfig
