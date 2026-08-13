"""Synchronous simulation and read-only dashboard data endpoints."""

from pathlib import Path

import duckdb
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from dataforge.api.dashboard.store import dashboard_payload, dashboard_store
from dataforge.export.analytical import (
    DuckDBAnalyticalSink,
    DuckDBOperationalAnalyticsSink,
)
from dataforge.runtime.runner import SimulationRunner
from dataforge.scenario.loader import load_scenario
from dataforge.scenario.resolution import resolve_scenario_path

router = APIRouter(prefix="/analytics", tags=["analytics"])
DASHBOARD_DIRECTORY = Path(__file__).parents[1] / "dashboard"


class AnalyticsRunRequest(BaseModel):
    scenario: str = Field(min_length=1)


class AnalyticsRunResponse(BaseModel):
    status: str
    scenario: str
    seed: int
    ticks_processed: int
    engine_executions: int
    net_sales_amount: str
    lost_sales_amount: str


@router.get("", response_class=FileResponse, include_in_schema=False)
def analytics_dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_DIRECTORY / "index.html")


@router.post("/run", response_model=AnalyticsRunResponse)
def run_analytics(request: AnalyticsRunRequest) -> AnalyticsRunResponse:
    """Synchronously replace the single dashboard run after successful completion."""
    scenario_path = resolve_scenario_path(Path(request.scenario))
    if not scenario_path.is_file():
        raise HTTPException(status_code=404, detail="Scenario file not found")
    connection = duckdb.connect(":memory:")
    try:
        scenario = load_scenario(scenario_path)
        sink = DuckDBOperationalAnalyticsSink(DuckDBAnalyticalSink(connection))
        result = SimulationRunner(scenario, sink=sink).run()
    except (ValidationError, yaml.YAMLError) as error:
        connection.close()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        connection.close()
        raise HTTPException(status_code=500, detail=str(error)) from error
    dashboard_store.install(connection, result, scenario_path)
    return AnalyticsRunResponse(
        status="ok",
        scenario=scenario_path.name,
        seed=scenario.simulation.seed,
        ticks_processed=result.simulation_summary.ticks_processed,
        engine_executions=result.simulation_summary.engine_executions,
        net_sales_amount=str(result.metrics_summary.net_sales_amount),
        lost_sales_amount=str(result.metrics_summary.lost_sales_amount),
    )


@router.get("/data")
def analytics_data() -> dict[str, object]:
    """Return grouped results from the closed set of supported Business Queries."""
    try:
        metadata, queries = dashboard_store.snapshot()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return dashboard_payload(metadata, queries)
