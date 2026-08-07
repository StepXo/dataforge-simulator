"""Synchronous local verification endpoint for the complete runtime."""

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from dataforge.runtime.runner import SimulationRunner
from dataforge.runtime.summary import build_simulation_summary

router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationVerifyRequest(BaseModel):
    """Reference a scenario file accessible to the application process."""

    scenario_path: str = Field(min_length=1)


class SimulationVerifyResponse(BaseModel):
    """Compact verification result without exposing simulation state."""

    status: Literal["ok"]
    seed: int
    start_datetime: datetime
    end_datetime: datetime
    tick_unit: str
    ticks_processed: int
    engine_executions: int
    validation_passed: bool
    demand_units: int
    unassigned_demand_units: int
    total_transactions: int
    completed_transactions: int
    partially_completed_transactions: int
    rejected_transactions: int
    transaction_lines: int
    completed_lines: int
    rejected_lines: int
    completed_units: int
    rejected_units: int
    net_sales_amount: str
    lost_sales_amount: str
    out_of_stock_signals: int
    replenishments_completed: int
    units_replenished: int


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
    return SimulationVerifyResponse(
        status="ok",
        seed=summary.seed,
        start_datetime=summary.start_datetime,
        end_datetime=summary.end_datetime,
        tick_unit=summary.tick_unit,
        ticks_processed=summary.ticks_processed,
        engine_executions=summary.engine_executions,
        validation_passed=True,
        demand_units=summary.demand_units,
        unassigned_demand_units=summary.unassigned_demand_units,
        total_transactions=summary.total_transactions,
        completed_transactions=summary.completed_transactions,
        partially_completed_transactions=summary.partially_completed_transactions,
        rejected_transactions=summary.rejected_transactions,
        transaction_lines=summary.transaction_lines,
        completed_lines=summary.completed_lines,
        rejected_lines=summary.rejected_lines,
        completed_units=summary.completed_units,
        rejected_units=summary.rejected_units,
        net_sales_amount=str(summary.net_sales_amount),
        lost_sales_amount=str(summary.lost_sales_amount),
        out_of_stock_signals=summary.out_of_stock_signals,
        replenishments_completed=summary.replenishments_completed,
        units_replenished=summary.units_replenished,
    )
