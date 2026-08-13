"""Background simulation and read-only dashboard data endpoints."""

import logging
from pathlib import Path
from threading import Thread
from time import monotonic

import duckdb
import yaml
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from dataforge.api.dashboard.store import dashboard_payload, dashboard_store
from dataforge.core.simulation_clock import SimulationClock
from dataforge.core.value_objects import TimeRange
from dataforge.export.analytical import (
    DuckDBAnalyticalSink,
    DuckDBOperationalAnalyticsSink,
)
from dataforge.runtime.runner import SimulationRunner
from dataforge.scenario.loader import load_scenario
from dataforge.scenario.models import ScenarioDefinition

router = APIRouter(prefix="/analytics", tags=["analytics"])
DASHBOARD_DIRECTORY = Path(__file__).parents[1] / "dashboard"
SCENARIO_DIRECTORY = Path("configs/scenarios").resolve()
LOGGER = logging.getLogger(__name__)


class AnalyticsRunRequest(BaseModel):
    scenario: str = Field(min_length=1)


class AnalyticsRunAccepted(BaseModel):
    status: str
    scenario: str
    current_tick: int
    total_ticks: int
    progress_percent: float


class AnalyticsRunStatus(BaseModel):
    status: str
    scenario: str | None
    current_tick: int
    total_ticks: int
    progress_percent: float
    simulated_time: str | None
    error: str | None


@router.get("", response_class=FileResponse, include_in_schema=False)
def analytics_dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_DIRECTORY / "index.html")


@router.get("/scenarios", response_model=list[str])
def analytics_scenarios() -> list[str]:
    """Discover logical scenario identifiers from the canonical directory."""
    if not SCENARIO_DIRECTORY.is_dir():
        return []
    return sorted(path.stem for path in SCENARIO_DIRECTORY.glob("*.yaml"))


@router.post(
    "/run",
    response_model=AnalyticsRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_analytics(request: AnalyticsRunRequest) -> AnalyticsRunAccepted:
    """Validate and launch one isolated analytical candidate in the background."""
    try:
        scenario_path = resolve_dashboard_scenario(request.scenario)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not scenario_path.is_file():
        raise HTTPException(status_code=404, detail="Scenario not found")
    try:
        scenario = load_scenario(scenario_path)
    except (ValidationError, yaml.YAMLError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    simulation = scenario.simulation
    clock = SimulationClock(
        TimeRange(simulation.start_datetime, simulation.end_datetime),
        simulation.tick_unit,
    )
    try:
        dashboard_store.begin(
            scenario_path, clock.total_ticks, simulation.start_datetime
        )
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    Thread(
        target=_execute_candidate,
        args=(scenario_path, scenario),
        name="dataforge-analytics-run",
        daemon=True,
    ).start()
    return AnalyticsRunAccepted(
        status="running",
        scenario=scenario_path.stem,
        current_tick=0,
        total_ticks=clock.total_ticks,
        progress_percent=0.0,
    )


@router.get("/status", response_model=AnalyticsRunStatus)
def analytics_status() -> AnalyticsRunStatus:
    """Return the coherent progress snapshot for the single dashboard candidate."""
    current = dashboard_store.status()
    return AnalyticsRunStatus(
        status=current.status,
        scenario=current.scenario,
        current_tick=current.current_tick,
        total_ticks=current.total_ticks,
        progress_percent=round(current.progress_percent, 2),
        simulated_time=(
            current.simulated_time.isoformat() if current.simulated_time else None
        ),
        error=current.error,
    )


@router.get("/data")
def analytics_data() -> dict[str, object]:
    """Return grouped results from the closed set of supported Business Queries."""
    try:
        metadata, queries = dashboard_store.snapshot()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return dashboard_payload(metadata, queries)


def resolve_dashboard_scenario(identifier: str) -> Path:
    """Resolve a logical name or canonical relative path without path traversal."""
    value = identifier.strip()
    if not value:
        raise ValueError("Scenario identifier cannot be empty")
    supplied = Path(value)
    if supplied.is_absolute():
        candidate = supplied.resolve()
    elif len(supplied.parts) == 1:
        filename = supplied.name
        if supplied.suffix and supplied.suffix.lower() != ".yaml":
            raise ValueError("Scenario must be a YAML file")
        candidate = SCENARIO_DIRECTORY / (
            filename if supplied.suffix else f"{filename}.yaml"
        )
    else:
        candidate = (Path.cwd() / supplied).resolve()
    try:
        candidate.relative_to(SCENARIO_DIRECTORY)
    except ValueError as error:
        raise ValueError("Scenario must be inside configs/scenarios") from error
    if candidate.suffix.lower() != ".yaml":
        raise ValueError("Scenario must be a YAML file")
    return candidate


def _execute_candidate(scenario_path: Path, scenario: ScenarioDefinition) -> None:
    started = monotonic()
    connection: duckdb.DuckDBPyConnection | None = None
    LOGGER.info(
        "Analytics run started: scenario=%s total_ticks=%s",
        scenario_path.name,
        dashboard_store.status().total_ticks,
    )
    try:
        connection = duckdb.connect(":memory:")
        sink = DuckDBOperationalAnalyticsSink(DuckDBAnalyticalSink(connection))
        result = SimulationRunner(
            scenario,
            sink=sink,
            progress_callback=dashboard_store.update_progress,
        ).run()
        dashboard_store.install(connection, result, scenario_path)
        connection = None
        LOGGER.info(
            "Analytics run completed: scenario=%s ticks=%s elapsed_seconds=%.2f",
            scenario_path.name,
            result.simulation_summary.ticks_processed,
            monotonic() - started,
        )
    except Exception as error:
        if connection is not None:
            connection.close()
            connection = None
        dashboard_store.fail(str(error))
        LOGGER.exception(
            "Analytics run failed: scenario=%s elapsed_seconds=%.2f",
            scenario_path.name,
            monotonic() - started,
        )
    finally:
        if connection is not None:
            connection.close()
