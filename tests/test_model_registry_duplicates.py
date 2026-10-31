"""The model registry refuses a version whose weights are already registered.

Registering the same checkpoint twice (or under a second name) creates rows that can never
differ in a benchmark, so both entry points - registering a training candidate and promoting
a run - answer 409 and leave no artifact copy behind.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import models

client = TestClient(app)

WEIGHTS = b"fake-policy-weights-bytes"


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Point the registry at a throwaway tree so the real one is never touched."""
    data = tmp_path / "frontend" / "public" / "data"
    training = tmp_path / "results" / "training"
    data.mkdir(parents=True)
    training.mkdir(parents=True)
    monkeypatch.setattr(models, "ROOT", tmp_path)
    monkeypatch.setattr(models, "DATA", data)
    monkeypatch.setattr(models, "TRAINING", training)
    monkeypatch.setattr(models, "CHECKPOINTS", tmp_path / "results" / "checkpoints")
    monkeypatch.setattr(models, "REGISTRY", tmp_path / "results" / "models.json")
    return tmp_path


def _training_run(root: Path, weights: bytes = WEIGHTS, seed: int = 41) -> None:
    seed_dir = root / "results" / "training" / "rl_shortpilot" / "sf_mission_2x2" / f"seed{seed}"
    (seed_dir / "checkpoints").mkdir(parents=True)
    checkpoint = seed_dir / "checkpoints" / "model_4096_steps.zip"
    checkpoint.write_bytes(weights)
    checkpoint.with_suffix(".json").write_text(json.dumps({"network": "sf_mission_2x2"}), encoding="utf-8")
    (seed_dir / "run_info.json").write_text(
        json.dumps(
            {
                "agent": "rl_shortpilot",
                "network": "sf_mission_2x2",
                "seed": seed,
                "total_timesteps": 4096,
                "recipe_hash": "abc",
                "config": {"label": "RL short pilot", "algorithm": "ppo"},
            }
        ),
        encoding="utf-8",
    )


def _promotable_run(root: Path, weights: bytes = WEIGHTS) -> None:
    checkpoint = root / "results" / "checkpoints" / "rl_shortpilot" / "sf_mission_2x2" / "seed41.zip"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(weights)
    checkpoint.with_suffix(".json").write_text(
        json.dumps({"network": "sf_mission_2x2", "training_seed": 41, "config": {"algorithm": "ppo"}}),
        encoding="utf-8",
    )
    (root / "frontend" / "public" / "data" / "runs.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "runId": "rl_shortpilot__sf_mission_2x2__seed41",
                        "name": "RL short pilot",
                        "network": "sf_mission_2x2",
                        "seed": 41,
                        "artifacts": {"checkpoint": checkpoint.relative_to(root).as_posix()},
                        "hyperparameters": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _register(name: str) -> object:
    return client.post(
        "/api/models/register-candidate",
        json={"candidate_id": "rl_shortpilot|sf_mission_2x2|41", "name": name},
    )


def _promote(name: str) -> object:
    return client.post(
        "/api/models/promote",
        json={"runId": "rl_shortpilot__sf_mission_2x2__seed41", "name": name},
    )


def _artifact_dirs(root: Path) -> list[Path]:
    models_root = root / "results" / "models"
    return sorted(models_root.iterdir()) if models_root.is_dir() else []


def test_registering_the_same_candidate_twice_is_refused(sandbox):
    _training_run(sandbox)

    first = _register("rl-shortpilot")
    assert first.status_code == 201, first.text
    assert first.json()["version"]["version"] == 1

    second = _register("rl-shortpilot")
    assert second.status_code == 409
    assert "already registered as rl-shortpilot v1" in second.json()["detail"]
    assert len(_artifact_dirs(sandbox)) == 1
    assert len(models.load_registry()["models"]["rl-shortpilot"]) == 1


def test_same_weights_under_a_second_name_are_refused(sandbox):
    """The duplicate that motivated this check: a second name for the same weights."""
    _training_run(sandbox)
    assert _register("generalist-shortpilot").status_code == 201

    duplicate = _register("generalist_shortpilot")
    assert duplicate.status_code == 409
    assert "generalist-shortpilot v1" in duplicate.json()["detail"]
    assert "identical SHA-256" in duplicate.json()["detail"]
    # Nothing was copied and no second name appeared.
    assert len(_artifact_dirs(sandbox)) == 1
    assert set(models.load_registry()["models"]) == {"generalist-shortpilot"}


def test_promote_refuses_weights_already_registered(sandbox):
    _training_run(sandbox)
    _promotable_run(sandbox)
    assert _register("generalist-shortpilot").status_code == 201

    duplicate = _promote("rl-shortpilot")
    assert duplicate.status_code == 409
    assert "generalist-shortpilot v1" in duplicate.json()["detail"]
    assert len(_artifact_dirs(sandbox)) == 1
    assert set(models.load_registry()["models"]) == {"generalist-shortpilot"}


def test_promote_refuses_the_same_run_twice(sandbox):
    _promotable_run(sandbox)
    assert _promote("rl-shortpilot").status_code == 201

    duplicate = _promote("rl-shortpilot")
    assert duplicate.status_code == 409
    assert "rl-shortpilot v1" in duplicate.json()["detail"]
    assert len(_artifact_dirs(sandbox)) == 1


def test_distinct_weights_under_two_names_are_allowed(sandbox):
    """The check is on the bytes, not the name - different weights still register."""
    _training_run(sandbox, weights=WEIGHTS)
    _training_run(sandbox, weights=WEIGHTS + b"-other", seed=42)
    assert _register("generalist-shortpilot").status_code == 201

    other = client.post(
        "/api/models/register-candidate",
        json={"candidate_id": "rl_shortpilot|sf_mission_2x2|42", "name": "generalist_shortpilot"},
    )
    assert other.status_code == 201, other.text
    assert set(models.load_registry()["models"]) == {"generalist-shortpilot", "generalist_shortpilot"}
