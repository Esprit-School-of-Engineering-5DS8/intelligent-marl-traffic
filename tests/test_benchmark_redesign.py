"""Tests for the live lab benchmark redesign endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_catalog_endpoint_returns_networks_and_controllers():
    response = client.get("/api/catalog")
    assert response.status_code == 200
    data = response.json()
    assert "networks" in data
    assert "agentConfigs" in data
    assert "controllers" in data

    network_names = [n["network"] for n in data["networks"]]
    assert "grid2x2" in network_names
    assert "grid3x3" in network_names
    assert "tunis" in network_names
    assert "monaco" in network_names

    # Verify controller strip availability on grid2x2
    grid2 = next(n for n in data["networks"] if n["network"] == "grid2x2")
    assert "mp" in grid2["controllers"]
    assert grid2["controllers"]["mp"]["available"] is True


def test_jobs_list_and_queue():
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_train_request_validation():
    # Unknown network should be refused
    response = client.post(
        "/api/train",
        json={"agent": "coop", "network": "invalid_net", "seeds": [1], "timesteps": 3000},
    )
    assert response.status_code == 400


def test_compare_request_validation():
    # Less than 2 methods should be rejected by pydantic
    response = client.post(
        "/api/compare",
        json={"network": "grid3x3", "methods": ["mp"]},
    )
    assert response.status_code == 422
