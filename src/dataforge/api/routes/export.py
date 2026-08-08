"""Synchronous server-side operational export endpoint."""

from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from dataforge.api.summary import SimulationSummaryFields, simulation_summary_data
from dataforge.export.files import ExportFormat, build_export_sink, export_dataset_count
from dataforge.runtime.runner import SimulationRunner
from dataforge.runtime.summary import build_simulation_summary
from dataforge.scenario.loader import load_scenario
from dataforge.scenario.resolution import resolve_scenario_path

router = APIRouter(prefix="/simulation", tags=["simulation"])
API_EXPORT_ROOT = Path("outputs")


class SimulationExportRequest(BaseModel):
    """Request one synchronous export into the server-local output root."""

    scenario: str = Field(min_length=1)
    format: ExportFormat
    output: str = Field(min_length=1)


class SimulationExportResponse(SimulationSummaryFields):
    """Report a completed server-side export and its simulation summary."""

    status: Literal["ok"]
    format: ExportFormat
    output: str
    datasets: int


@router.post("/export", response_model=SimulationExportResponse)
def export_simulation(request: SimulationExportRequest) -> SimulationExportResponse:
    """Run one scenario and export incrementally to the local server filesystem."""
    scenario_path = resolve_scenario_path(Path(request.scenario))
    if not scenario_path.is_file():
        raise HTTPException(status_code=404, detail="Scenario file not found")
    try:
        output_directory = resolve_api_output(request.output)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        scenario = load_scenario(scenario_path)
        sink = build_export_sink(request.format, output_directory)
        result = SimulationRunner(scenario, sink=sink).run()
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValidationError, yaml.YAMLError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    summary = build_simulation_summary(result)
    if not summary.validation_passed:
        raise HTTPException(status_code=500, detail="Final state validation is missing")
    return SimulationExportResponse.model_validate(
        {
            "status": "ok",
            "format": request.format,
            "output": str(API_EXPORT_ROOT / request.output),
            "datasets": export_dataset_count(),
            **simulation_summary_data(summary),
        }
    )


def resolve_api_output(output: str) -> Path:
    """Resolve one relative output below the server-controlled export root."""
    root = API_EXPORT_ROOT.resolve()
    requested = Path(output)
    if requested.is_absolute():
        raise ValueError("Export output must be relative to the server output root")
    target = (root / requested).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("Export output must stay inside the server output root")
    return target
