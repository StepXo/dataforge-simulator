"""Backend and integration coverage for the completed-run dashboard."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import MagicMock

import pytest
import yaml
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
    script = client.get("/analytics/assets/dashboard.js")
    assert script.status_code == 200
    assert "setInterval(pollStatus, 10000)" in script.text
    assert 'button").disabled = running' in script.text


def test_dashboard_data_requires_a_completed_run_and_exposes_no_sql_endpoint() -> None:
    response = client.get("/analytics/data")

    assert response.status_code == 404
    assert "No completed analytical run" in response.json()["detail"]
    assert client.post("/analytics/sql", json={"sql": "SELECT 1"}).status_code == 404
    assert client.post("/sql", json={"sql": "SELECT 1"}).status_code == 404


def test_scenario_discovery_and_safe_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_file(tmp_path / "first")
    root = tmp_path / "first/scenarios"
    (root / "notes.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr(analytics_routes, "SCENARIO_DIRECTORY", root.resolve())

    assert client.get("/analytics/scenarios").json() == ["runtime"]
    assert (
        analytics_routes.resolve_dashboard_scenario("runtime") == root / "runtime.yaml"
    )
    assert (
        analytics_routes.resolve_dashboard_scenario("runtime.yaml")
        == root / "runtime.yaml"
    )
    assert (
        analytics_routes.resolve_dashboard_scenario(str(root / "runtime.yaml"))
        == root / "runtime.yaml"
    )
    assert not analytics_routes.resolve_dashboard_scenario("unknown").is_file()
    assert (
        client.post("/analytics/run", json={"scenario": "unknown"}).status_code == 404
    )
    with pytest.raises(ValueError, match="inside configs/scenarios"):
        analytics_routes.resolve_dashboard_scenario("../../something")
    traversal = client.post("/analytics/run", json={"scenario": "../../something"})
    assert traversal.status_code == 422


def test_simulation_business_queries_and_dashboard_reconcile_net_revenue() -> None:
    run_response = client.post("/analytics/run", json={"scenario": "smoke-test"})

    assert run_response.status_code == 202, run_response.text
    assert run_response.json()["status"] == "running"
    completed = wait_for_status("completed")
    assert completed["progress_percent"] == 100
    assert completed["current_tick"] == completed["total_ticks"]
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
    assert metadata.scenario == "smoke-test.yaml"
    assert dashboard_total == business_total
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


def test_successive_dashboard_runs_replace_the_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = scenario_file(tmp_path, seed=11).resolve()
    root = first.parent
    first_target = root / "first.yaml"
    first_target.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    second_target = root / "second.yaml"
    second_content = yaml.safe_load(first.read_text(encoding="utf-8"))
    second_content["simulation"]["seed"] = 22
    second_target.write_text(yaml.safe_dump(second_content), encoding="utf-8")
    monkeypatch.setattr(analytics_routes, "SCENARIO_DIRECTORY", root.resolve())

    first_response = client.post("/analytics/run", json={"scenario": "first"})
    wait_for_status("completed")
    second_response = client.post("/analytics/run", json={"scenario": "second.yaml"})
    wait_for_status("completed")

    assert first_response.status_code == 202, first_response.text
    assert second_response.status_code == 202, second_response.text
    body = client.get("/analytics/data").json()
    assert body["run"]["scenario"] == second_target.name
    assert body["run"]["seed"] == 22


def test_failed_candidate_is_closed_and_keeps_previous_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = scenario_file(tmp_path / "valid", seed=31).resolve()
    root = valid.parent
    monkeypatch.setattr(analytics_routes, "SCENARIO_DIRECTORY", root.resolve())
    response = client.post("/analytics/run", json={"scenario": valid.stem})
    assert response.status_code == 202, response.text
    wait_for_status("completed")
    before = client.get("/analytics/data").json()["run"]
    candidate = MagicMock()

    monkeypatch.setattr(analytics_routes.duckdb, "connect", lambda _: candidate)
    monkeypatch.setattr(
        analytics_routes.SimulationRunner,
        "run",
        lambda _: (_ for _ in ()).throw(RuntimeError("candidate failed")),
    )

    failed = client.post("/analytics/run", json={"scenario": valid.stem})

    assert failed.status_code == 202
    status = wait_for_status("failed")
    assert status["error"] == "candidate failed"
    candidate.close.assert_called_once_with()
    assert client.get("/analytics/data").json()["run"] == before


def test_running_candidate_reports_progress_and_rejects_concurrent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = Event()

    def blocked_candidate(path: Path, scenario: object) -> None:
        del path, scenario
        dashboard_store.update_progress(1, 24, datetime(2024, 1, 1))
        release.wait(timeout=5)
        dashboard_store.fail("test completed")

    monkeypatch.setattr(analytics_routes, "_execute_candidate", blocked_candidate)

    started = monotonic()
    first = client.post("/analytics/run", json={"scenario": "smoke-test"})
    elapsed = monotonic() - started
    current = client.get("/analytics/status").json()
    second = client.post("/analytics/run", json={"scenario": "smoke-test"})
    release.set()

    assert first.status_code == 202
    assert elapsed < 1
    assert current["status"] == "running"
    assert 0 <= current["current_tick"] <= current["total_ticks"]
    assert 0 <= current["progress_percent"] <= 100
    assert second.status_code == 409
    wait_for_status("failed")


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


def wait_for_status(expected: str, timeout: float = 10) -> dict[str, object]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        body = client.get("/analytics/status").json()
        if body["status"] == expected:
            return body
        sleep(0.01)
    raise AssertionError(f"Dashboard status did not become {expected}")
