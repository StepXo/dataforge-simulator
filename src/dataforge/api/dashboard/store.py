"""Single-run in-process analytical store for the non-live dashboard."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Literal

import duckdb

from dataforge.analytics.business import (
    BusinessQuery,
    BusinessQueryRow,
    run_business_query,
)
from dataforge.runtime.result import SimulationResult


@dataclass(frozen=True, slots=True)
class DashboardRunMetadata:
    scenario: str
    seed: int
    start: datetime
    end: datetime
    tick_unit: str
    ticks_processed: int
    engine_executions: int


@dataclass(frozen=True, slots=True)
class DashboardRunStatus:
    status: Literal["idle", "running", "completed", "failed"]
    scenario: str | None
    current_tick: int
    total_ticks: int
    progress_percent: float
    simulated_time: datetime | None
    error: str | None


class AnalyticsDashboardStore:
    """Retain one completed in-memory analytical run across API requests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._metadata: DashboardRunMetadata | None = None
        self._status = DashboardRunStatus("idle", None, 0, 0, 0.0, None, None)

    def begin(
        self,
        scenario_path: Path,
        total_ticks: int,
        start_time: datetime,
    ) -> None:
        """Reserve the single candidate execution without replacing current data."""
        with self._lock:
            if self._status.status == "running":
                raise RuntimeError("An analytical run is already in progress")
            self._status = DashboardRunStatus(
                "running",
                scenario_path.name,
                0,
                total_ticks,
                0.0,
                start_time,
                None,
            )

    def update_progress(
        self, completed_ticks: int, total_ticks: int, simulated_time: datetime
    ) -> None:
        """Publish one successfully completed tick from the background run."""
        with self._lock:
            if self._status.status != "running":
                return
            progress = 100.0 * completed_ticks / total_ticks
            self._status = DashboardRunStatus(
                "running",
                self._status.scenario,
                completed_ticks,
                total_ticks,
                progress,
                simulated_time,
                None,
            )

    def install(
        self,
        connection: duckdb.DuckDBPyConnection,
        result: SimulationResult,
        scenario_path: Path,
    ) -> None:
        simulation = result.scenario.simulation
        metadata = DashboardRunMetadata(
            scenario=scenario_path.name,
            seed=simulation.seed,
            start=simulation.start_datetime,
            end=simulation.end_datetime,
            tick_unit=simulation.tick_unit.value,
            ticks_processed=result.simulation_summary.ticks_processed,
            engine_executions=result.simulation_summary.engine_executions,
        )
        with self._lock:
            previous = self._connection
            self._connection = connection
            self._metadata = metadata
            self._status = DashboardRunStatus(
                "completed",
                scenario_path.name,
                result.simulation_summary.ticks_processed,
                result.simulation_summary.ticks_processed,
                100.0,
                simulation.end_datetime,
                None,
            )
            if previous is not None:
                previous.close()

    def fail(self, error: str) -> None:
        """Publish candidate failure while retaining the last completed database."""
        with self._lock:
            self._status = DashboardRunStatus(
                "failed",
                self._status.scenario,
                self._status.current_tick,
                self._status.total_ticks,
                self._status.progress_percent,
                self._status.simulated_time,
                error,
            )

    def status(self) -> DashboardRunStatus:
        """Return one coherent immutable progress snapshot."""
        with self._lock:
            return self._status

    def snapshot(
        self,
    ) -> tuple[
        DashboardRunMetadata,
        dict[BusinessQuery, tuple[BusinessQueryRow, ...]],
    ]:
        with self._lock:
            if self._connection is None or self._metadata is None:
                raise LookupError("No completed analytical run is available")
            queries = {
                query: run_business_query(self._connection, query)
                for query in BusinessQuery
            }
            return self._metadata, queries

    def reset(self) -> None:
        """Release the active run; used by application shutdown and tests."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._metadata = None
            self._status = DashboardRunStatus("idle", None, 0, 0, 0.0, None, None)


dashboard_store = AnalyticsDashboardStore()


def dashboard_payload(
    metadata: DashboardRunMetadata,
    queries: dict[BusinessQuery, tuple[BusinessQueryRow, ...]],
) -> dict[str, object]:
    """Group existing business-query results for the small web UI."""
    revenue = queries[BusinessQuery.REVENUE_BY_LOCATION]
    channels = queries[BusinessQuery.CHANNEL_PERFORMANCE]
    overview: dict[str, dict[str, object]] = {}
    for row in revenue:
        currency = _string(row, "currency")
        values = overview.setdefault(currency, _empty_overview(currency))
        values["net_revenue"] = _decimal(values, "net_revenue") + _decimal(
            row, "net_sales"
        )
        values["gross_revenue"] = _decimal(values, "gross_revenue") + _decimal(
            row, "gross_sales"
        )
        values["discount_amount"] = _decimal(values, "discount_amount") + _decimal(
            row, "discount_amount"
        )
        values["completed_units"] = _integer(values, "completed_units") + _integer(
            row, "completed_units"
        )
    for row in channels:
        currency = _string(row, "currency")
        values = overview.setdefault(currency, _empty_overview(currency))
        values["lost_sales"] = _decimal(values, "lost_sales") + _decimal(
            row, "lost_sales"
        )
        values["baskets"] = _integer(values, "baskets") + _integer(row, "baskets")

    lost_by_location = {
        (_string(row, "location_id"), _string(row, "currency")): _decimal(
            row, "lost_sales"
        )
        for row in queries[BusinessQuery.LOST_SALES_BY_LOCATION]
    }
    locations = tuple(
        {
            **row,
            "lost_sales": lost_by_location.get(
                (_string(row, "location_id"), _string(row, "currency")),
                Decimal("0.00"),
            ),
        }
        for row in revenue
    )
    payload: dict[str, object] = {
        "run": {
            "scenario": metadata.scenario,
            "seed": metadata.seed,
            "start": metadata.start,
            "end": metadata.end,
            "tick_unit": metadata.tick_unit,
            "ticks_processed": metadata.ticks_processed,
            "engine_executions": metadata.engine_executions,
        },
        "overview": tuple(overview[currency] for currency in sorted(overview)),
        "sales": {
            "daily": queries[BusinessQuery.DAILY_SALES],
            "monthly": queries[BusinessQuery.MONTHLY_SALES],
        },
        "locations": locations,
        "products": queries[BusinessQuery.PRODUCT_PERFORMANCE],
        "categories": queries[BusinessQuery.CATEGORY_PERFORMANCE],
        "lost_sales": {
            "products": queries[BusinessQuery.LOST_SALES_BY_PRODUCT],
            "locations": queries[BusinessQuery.LOST_SALES_BY_LOCATION],
            "reasons": queries[BusinessQuery.LOST_SALES_BY_REASON],
        },
        "customers": queries[BusinessQuery.CUSTOMER_PURCHASE_ANALYSIS],
        "channels": channels,
        "inventory": {
            "summary": queries[BusinessQuery.INVENTORY_MOVEMENT_SUMMARY],
            "products": queries[BusinessQuery.INVENTORY_MOVEMENT_BY_PRODUCT],
            "locations": queries[BusinessQuery.INVENTORY_MOVEMENT_BY_LOCATION],
            "replenishment": queries[BusinessQuery.REPLENISHMENT_PERFORMANCE],
        },
        "promotions": {
            "summary": queries[BusinessQuery.PROMOTED_SALES_SUMMARY],
            "associations": queries[BusinessQuery.PROMOTION_ASSOCIATED_SALES],
        },
    }
    serialized = _json_value(payload)
    if not isinstance(serialized, dict):
        raise TypeError("Dashboard payload must remain a mapping")
    return serialized


def _empty_overview(currency: str) -> dict[str, object]:
    return {
        "currency": currency,
        "net_revenue": Decimal("0.00"),
        "gross_revenue": Decimal("0.00"),
        "discount_amount": Decimal("0.00"),
        "completed_units": 0,
        "lost_sales": Decimal("0.00"),
        "baskets": 0,
    }


def _string(values: Mapping[str, object], name: str) -> str:
    value = values[name]
    if not isinstance(value, str):
        raise ValueError(f"Dashboard value must be a string: {name}")
    return value


def _decimal(values: Mapping[str, object], name: str) -> Decimal:
    value = values[name]
    if not isinstance(value, Decimal):
        raise ValueError(f"Dashboard value must be Decimal: {name}")
    return value


def _integer(values: Mapping[str, object], name: str) -> int:
    value = values[name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Dashboard value must be an integer: {name}")
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value
