"""The dashboard's control-policy contract (GET/PUT /api/policy).

These replace the tests of the retired ``environment``/``baselines`` stack: what the
dashboard relies on is that an unavailable controller is refused instead of silently
downgraded, and that the LLM degrades to Max-Pressure rather than failing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import policy
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Never touch the developer's saved policy while testing."""
    monkeypatch.setattr(policy, "POLICY_STATE", tmp_path / "dashboard_policy.json")
    yield


def test_health_reports_data_presence():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_policy_reports_catalog_and_networks():
    body = client.get("/api/policy").json()
    assert body["method"] in policy.METHODS
    assert body["network"] in policy.NETWORKS
    assert {entry["method"] for entry in body["catalog"]} == set(policy.METHODS)
    assert body["available"] is True


def test_unknown_method_is_refused():
    response = client.put("/api/policy", json={"method": "nope"})
    assert response.status_code == 422
    assert "unknown method" in response.json()["detail"]


def test_unknown_network_is_refused():
    response = client.put("/api/policy", json={"method": "mp", "network": "grid128x128"})
    assert response.status_code == 422
    assert "unknown network" in response.json()["detail"]


def test_learned_method_without_checkpoint_is_refused():
    response = client.put("/api/policy", json={"method": "dqn", "network": "grid2x2"})
    assert response.status_code == 422
    assert "no trained dqn model for grid2x2" in response.json()["detail"]


def test_valid_baseline_round_trips():
    response = client.put("/api/policy", json={"method": "mp", "network": "grid3x3"})
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "mp"
    assert body["available"] is True
    assert client.get("/api/policy").json()["method"] == "mp"


def test_llm_without_a_key_stays_runnable_but_degraded(monkeypatch):
    monkeypatch.setenv("COTRAFFIC_LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    response = client.put("/api/policy", json={"method": "llm", "network": "grid2x2"})
    assert response.status_code == 200
    body = response.json()
    # It starts (falling back to Max-Pressure per call) instead of refusing the run.
    assert body["available"] is True
    assert body["degraded"] is True
    assert "GEMINI_API_KEY" in body["reason"]
