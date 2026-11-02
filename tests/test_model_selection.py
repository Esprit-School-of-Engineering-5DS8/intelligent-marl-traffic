"""Selecting trained weights for the live policy.

Contract under test:

* ``GET /api/models/catalog`` lists the checkpoints a run can use;
* ``PUT /api/policy`` accepts an explicit ``checkpoint`` and persists it;
* a checkpoint outside ``results/``, a missing file, or weights trained for another
  network are refused with a message the UI can show.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api import policy
from api.main import app

client = TestClient(app)

NETWORK = "sf_mission_3x3"
OTHER_NETWORK = "tunis"


def _fake_checkpoint(method: str, network: str) -> object:
    """A weights file + agent-config sidecar exactly where ``cotraffic select`` writes.

    The seed number is high so a real training seed is never overwritten by the test.
    """
    folder = policy.CHECKPOINTS_DIR / method / network
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / f"seed{90 + uuid.uuid4().int % 9}.zip"
    checkpoint.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    checkpoint.with_suffix(".json").write_text(
        json.dumps(
            {"network": network, "config": {"label": f"{method} pytest", "algorithm": "ppo"}}
        ),
        encoding="utf-8",
    )
    return checkpoint


def _cleanup(checkpoint) -> None:
    checkpoint.unlink(missing_ok=True)
    checkpoint.with_suffix(".json").unlink(missing_ok=True)


@pytest.fixture()
def checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "POLICY_STATE", tmp_path / "dashboard_policy.json")
    method = policy.LEARNED[0]
    path = _fake_checkpoint(method, NETWORK)
    yield method, path
    _cleanup(path)


def test_catalog_lists_the_selectable_checkpoint(checkpoint):
    method, path = checkpoint
    body = client.get("/api/models/catalog", params={"network": NETWORK}).json()
    assert body["network"] == NETWORK
    entries = {entry["checkpointPath"]: entry for entry in body["models"]}
    assert str(path.resolve()) in entries
    entry = entries[str(path.resolve())]
    assert entry["agent"] == method
    assert entry["available"] is True
    assert entry["network"] == NETWORK
    assert entry["hasAgentConfig"] is True


def test_selecting_a_checkpoint_persists_it(checkpoint):
    method, path = checkpoint
    response = client.put(
        "/api/policy",
        json={"method": method, "network": NETWORK, "checkpoint": str(path)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checkpoint"] == str(path.resolve())
    assert body["checkpointSource"] == "explicit"
    # A restart must not lose the choice: the state file is current()'s only input.
    assert policy.current()["checkpoint"] == str(path.resolve())


def test_auto_returns_to_the_default_checkpoint(checkpoint):
    method, path = checkpoint
    client.put("/api/policy", json={"method": method, "network": NETWORK, "checkpoint": str(path)})
    body = client.put(
        "/api/policy", json={"method": method, "network": NETWORK, "checkpoint": "auto"}
    ).json()
    assert body["checkpointSource"] == "auto"
    assert body["checkpoint"] is None or body["checkpoint"].endswith("seed1.zip")


def test_checkpoint_outside_results_is_refused(tmp_path):
    outside = tmp_path / "weights.zip"
    outside.write_bytes(b"PK\x05\x06")
    response = client.put(
        "/api/policy",
        json={"method": "mp", "network": NETWORK, "checkpoint": str(outside)},
    )
    assert response.status_code == 422
    assert "must live under" in response.json()["detail"]


def test_missing_checkpoint_is_refused():
    missing = policy.CHECKPOINTS_DIR / "rl" / NETWORK / "does-not-exist.zip"
    response = client.put(
        "/api/policy",
        json={"method": policy.LEARNED[0], "network": NETWORK, "checkpoint": str(missing)},
    )
    assert response.status_code == 422
    assert "checkpoint not found" in response.json()["detail"]


def test_weights_trained_for_another_network_are_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "POLICY_STATE", tmp_path / "dashboard_policy.json")
    method = policy.LEARNED[0]
    path = _fake_checkpoint(method, OTHER_NETWORK)
    try:
        response = client.put(
            "/api/policy",
            json={"method": method, "network": NETWORK, "checkpoint": str(path)},
        )
        assert response.status_code == 422
        assert OTHER_NETWORK in response.json()["detail"]
    finally:
        _cleanup(path)
