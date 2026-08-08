"""Synchronous local verification endpoint for the complete runtime."""

from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from dataforge.api.summary import SimulationSummaryFields, simulation_summary_data
from dataforge.runtime.runner import SimulationRunner
from dataforge.runtime.summary import build_simulation_summary

router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationVerifyRequest(BaseModel):
    """Reference a scenario file accessible to the application process."""

    scenario_path: str = Field(min_length=1)


class SimulationVerifyResponse(SimulationSummaryFields):
    """Compact verification result without exposing simulation state."""

    status: Literal["ok"]


@router.post("/verify", response_model=SimulationVerifyResponse)
def verify_simulation(request: SimulationVerifyRequest) -> SimulationVerifyResponse:
    """Run a local scenario synchronously through the standard composition root."""
    scenario_path = Path(request.scenario_path)
    if not scenario_path.is_file():
        raise HTTPException(status_code=404, detail="Scenario file not found")

    try:
        result = SimulationRunner.from_file(scenario_path).run()
    except (ValidationError, yaml.YAMLError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    summary = build_simulation_summary(result)
    if not summary.validation_passed:
        raise HTTPException(status_code=500, detail="Final state validation is missing")
    return SimulationVerifyResponse.model_validate(
        {"status": "ok", **simulation_summary_data(summary)}
    )
