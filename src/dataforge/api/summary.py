"""Shared typed simulation summary fields for API responses."""

from datetime import datetime

from pydantic import BaseModel

from dataforge.runtime.summary import SimulationRuntimeSummary


class SimulationSummaryFields(BaseModel):
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


def simulation_summary_data(
    summary: SimulationRuntimeSummary,
) -> dict[str, object]:
    """Map one official runtime summary for all API surfaces."""
    return {
        "seed": summary.seed,
        "start_datetime": summary.start_datetime,
        "end_datetime": summary.end_datetime,
        "tick_unit": summary.tick_unit,
        "ticks_processed": summary.ticks_processed,
        "engine_executions": summary.engine_executions,
        "validation_passed": summary.validation_passed,
        "demand_units": summary.demand_units,
        "unassigned_demand_units": summary.unassigned_demand_units,
        "total_transactions": summary.total_transactions,
        "completed_transactions": summary.completed_transactions,
        "partially_completed_transactions": summary.partially_completed_transactions,
        "rejected_transactions": summary.rejected_transactions,
        "transaction_lines": summary.transaction_lines,
        "completed_lines": summary.completed_lines,
        "rejected_lines": summary.rejected_lines,
        "completed_units": summary.completed_units,
        "rejected_units": summary.rejected_units,
        "net_sales_amount": str(summary.net_sales_amount),
        "lost_sales_amount": str(summary.lost_sales_amount),
        "out_of_stock_signals": summary.out_of_stock_signals,
        "replenishments_completed": summary.replenishments_completed,
        "units_replenished": summary.units_replenished,
    }
