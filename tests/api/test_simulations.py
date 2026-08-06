"""Integration tests for simulation preview endpoints."""

import pytest
from fastapi.testclient import TestClient

from dataforge.main import app

client = TestClient(app)

VALID_REQUEST = {
    "seed": 42,
    "start_date": "2026-01-01",
    "end_date": "2026-01-07",
    "entity_count": 5,
}


def test_create_preview() -> None:
    response = client.post("/simulations/preview", json=VALID_REQUEST)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["simulation_id"] == "preview-42"
    assert body["seed"] == 42
    assert body["period"] == {
        "start_date": "2026-01-01",
        "end_date": "2026-01-07",
        "days": 7,
    }
    assert len(body["entities"]) == 5
    assert [entity["id"] for entity in body["entities"]] == [
        "entity-001",
        "entity-002",
        "entity-003",
        "entity-004",
        "entity-005",
    ]
    assert all(0.50 <= entity["activity_factor"] <= 1.50 for entity in body["entities"])


def test_same_request_produces_identical_response() -> None:
    first_response = client.post("/simulations/preview", json=VALID_REQUEST)
    second_response = client.post("/simulations/preview", json=VALID_REQUEST)

    assert first_response.json() == second_response.json()


def test_different_seed_changes_entities() -> None:
    first_response = client.post("/simulations/preview", json=VALID_REQUEST)
    second_response = client.post(
        "/simulations/preview", json={**VALID_REQUEST, "seed": 43}
    )

    assert first_response.json()["entities"] != second_response.json()["entities"]


@pytest.mark.parametrize(
    "invalid_request",
    [
        {**VALID_REQUEST, "end_date": "2025-12-31"},
        {**VALID_REQUEST, "entity_count": 0},
        {**VALID_REQUEST, "entity_count": 1001},
        {**VALID_REQUEST, "seed": -1},
        {**VALID_REQUEST, "seed": 4_294_967_296},
        {key: value for key, value in VALID_REQUEST.items() if key != "seed"},
    ],
)
def test_invalid_request_returns_422(invalid_request: dict[str, object]) -> None:
    response = client.post("/simulations/preview", json=invalid_request)

    assert response.status_code == 422
