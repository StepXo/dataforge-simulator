"""Integration tests for synchronous runtime verification."""

from pathlib import Path

from fastapi.testclient import TestClient

from dataforge.main import app
from tests.runtime.test_simulation_runner import scenario_file

client = TestClient(app)


def test_simulation_verify_runs_complete_pipeline(tmp_path: Path) -> None:
    path = scenario_file(tmp_path)

    response = client.post("/simulation/verify", json={"scenario_path": str(path)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["seed"] == 42
    assert body["tick_unit"] == "hour"
    assert body["ticks_processed"] == 2
    assert body["engine_executions"] == body["ticks_processed"] * 10
    assert body["validation_passed"] is True
    assert isinstance(body["net_sales_amount"], str)
    assert isinstance(body["lost_sales_amount"], str)


def test_simulation_verify_missing_scenario_returns_404(tmp_path: Path) -> None:
    response = client.post(
        "/simulation/verify",
        json={"scenario_path": str(tmp_path / "missing.yaml")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Scenario file not found"}


def test_simulation_verify_invalid_scenario_returns_422(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("simulation: [", encoding="utf-8")

    response = client.post("/simulation/verify", json={"scenario_path": str(path)})

    assert response.status_code == 422
    assert "detail" in response.json()
