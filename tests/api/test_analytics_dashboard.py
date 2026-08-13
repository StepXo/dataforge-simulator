"""Backend and integration coverage for the completed-run dashboard."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dataforge.analytics.business import BusinessQuery, run_business_query
from dataforge.api.app import app
from dataforge.api.dashboard.store import (
    DashboardRunMetadata,
    dashboard_payload,
    dashboard_store,
)
from dataforge.api.routes import analytics as analytics_routes
from dataforge.export.analytical import DuckDBAnalyticalSink
from tests.analytics.business.test_business_queries import analytical_fixture
from tests.runtime.test_simulation_runner import scenario_file

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_dashboard_store() -> Iterator[None]:
    dashboard_store.reset()
    yield
    dashboard_store.reset()


def test_dashboard_page_is_served_without_frontend_framework() -> None:
    response = client.get("/analytics")

    assert response.status_code == 200
    assert "DataForge Synthetic Business Analytics" in response.text
    assert "/analytics/assets/dashboard.js" in response.text
    assert client.get("/analytics/assets/dashboard.css").status_code == 200
    assert client.get("/analytics/assets/dashboard.js").status_code == 200


def test_dashboard_data_requires_a_completed_run_and_exposes_no_sql_endpoint() -> None:
    response = client.get("/analytics/data")

    assert response.status_code == 404
    assert "No completed analytical run" in response.json()["detail"]
    assert client.post("/analytics/sql", json={"sql": "SELECT 1"}).status_code == 404
    assert client.post("/sql", json={"sql": "SELECT 1"}).status_code == 404


def test_simulation_business_queries_and_dashboard_reconcile_net_revenue(
    tmp_path: Path,
) -> None:
    scenario = scenario_file(tmp_path / "scenario").resolve()
    run_response = client.post("/analytics/run", json={"scenario": str(scenario)})

    assert run_response.status_code == 200, run_response.text
    data_response = client.get("/analytics/data")
    assert data_response.status_code == 200, data_response.text
    body = data_response.json()
    dashboard_total = sum(
        (Decimal(row["net_revenue"]) for row in body["overview"]),
        start=Decimal("0.00"),
    )
    metadata, queries = dashboard_store.snapshot()
    business_total = sum(
        (
            _decimal(row["net_sales"])
            for row in queries[BusinessQuery.REVENUE_BY_LOCATION]
        ),
        start=Decimal("0.00"),
    )
    assert metadata.scenario == scenario.name
    assert dashboard_total == business_total
    assert dashboard_total == Decimal(run_response.json()["net_sales_amount"])
    assert {
        "sales",
        "locations",
        "products",
        "categories",
        "lost_sales",
        "customers",
        "channels",
        "inventory",
        "promotions",
    } <= body.keys()


def test_successive_dashboard_runs_replace_the_completed_run(tmp_path: Path) -> None:
    first = scenario_file(tmp_path / "first", seed=11).resolve()
    second = scenario_file(tmp_path / "second", seed=22).resolve()

    first_response = client.post("/analytics/run", json={"scenario": str(first)})
    second_response = client.post("/analytics/run", json={"scenario": str(second)})

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    body = client.get("/analytics/data").json()
    assert body["run"]["scenario"] == second.name
    assert body["run"]["seed"] == 22


def test_failed_candidate_is_closed_and_keeps_previous_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = scenario_file(tmp_path / "valid", seed=31).resolve()
    response = client.post("/analytics/run", json={"scenario": str(valid)})
    assert response.status_code == 200, response.text
    before = client.get("/analytics/data").json()["run"]
    candidate = MagicMock()

    monkeypatch.setattr(analytics_routes.duckdb, "connect", lambda _: candidate)
    monkeypatch.setattr(
        analytics_routes.SimulationRunner,
        "run",
        lambda _: (_ for _ in ()).throw(RuntimeError("candidate failed")),
    )

    failed = client.post("/analytics/run", json={"scenario": str(valid)})

    assert failed.status_code == 500
    assert failed.json()["detail"] == "candidate failed"
    candidate.close.assert_called_once_with()
    assert client.get("/analytics/data").json()["run"] == before


def test_dashboard_payload_keeps_currencies_separate_and_promotions_observational() -> (
    None
):
    sink = DuckDBAnalyticalSink(":memory:")
    sink.write_batch(analytical_fixture())
    queries = {
        query: run_business_query(sink.connection, query) for query in BusinessQuery
    }
    metadata = DashboardRunMetadata(
        "scenario.yaml",
        42,
        datetime(2024, 1, 1),
        datetime(2024, 2, 1),
        "hour",
        744,
        7440,
    )

    payload = dashboard_payload(metadata, queries)

    overview = payload["overview"]
    assert isinstance(overview, list)
    by_currency = {row["currency"]: row for row in overview}
    assert by_currency["USD"]["net_revenue"] == "180.0000"
    assert by_currency["USD"]["baskets"] == 3
    assert by_currency["EUR"]["net_revenue"] == "70.0000"
    promotions = payload["promotions"]
    assert isinstance(promotions, dict)
    assert "summary" in promotions and "associations" in promotions
    assert "lift" not in str(promotions).lower()
    sink.close()


def _decimal(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError("Expected Decimal business measure")
    return value
