"""Side-by-side runs accept free-hand saved checkpoints.

The comparison tab must be able to run any two saved models, whatever agent or
hyperparameters produced them. ``POST /api/runs`` therefore accepts a controller
id, ``model:<name>[@vN]`` from the registry, or ``checkpoint:<path under results/>``.
These tests pin the refusals: no shell-path escape, no unknown model, and no
weights trained on a different network.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import policy
from api.main import app

client = TestClient(app)
BASE = {
    "network": "sf_mission_2x2",
    "demand": "peak",
    "events": [],
    "seed": 3,
    "right": "mp",
}


def _post(**overrides):
    return client.post("/api/runs", json={**BASE, **overrides})


def test_unknown_controller_is_refused():
    assert _post(left="not-a-controller").status_code == 422


def test_checkpoint_outside_results_is_refused(tmp_path):
    outside = tmp_path / "weights.zip"
    outside.write_bytes(b"PK\x05\x06")
    response = _post(left=f"checkpoint:{outside}")
    assert response.status_code == 422
    assert "results" in response.text


def test_unknown_registry_model_is_refused():
    response = _post(left="model:model-that-does-not-exist")
    assert response.status_code == 422


def test_weights_from_another_network_are_refused():
    folder = policy.CHECKPOINTS_DIR / "generalist" / "sf_mission_3x3"
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint: Path = folder / "seed88.zip"
    checkpoint.write_bytes(b"PK\x05\x06")
    checkpoint.with_suffix(".json").write_text(
        json.dumps({"network": "sf_mission_3x3", "config": {"label": "pytest"}}),
        encoding="utf-8",
    )
    try:
        response = _post(left=f"checkpoint:{checkpoint}")
        assert response.status_code == 422
        assert "trained for" in response.text
    finally:
        checkpoint.unlink(missing_ok=True)
        checkpoint.with_suffix(".json").unlink(missing_ok=True)
