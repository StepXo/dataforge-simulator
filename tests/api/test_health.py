"""Tests for the health-check endpoint."""

from fastapi.testclient import TestClient

from dataforge.main import app

client = TestClient(app)


def test_ping() -> None:
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "pong"}
    assert response.headers["content-type"] == "application/json"
