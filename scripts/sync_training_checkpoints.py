#!/usr/bin/env python
"""Populate results/checkpoints/generalist/<network>/seed<k>.zip from the
final checkpoint of each completed training run, and also mirror the completed
candidates into results/models.json so the dashboard can pick them up when it
restarts even if the live register endpoint isn't reachable.

_run_training() writes the last checkpoint as model_<actual_steps>_steps.zip
(e.g. 502272), but _training_candidates() looks for the sidecar whose name
matches total_timesteps (model_500000_steps.zip). Sync the sidecar name so
the Make tab's 'Use this checkpoint' buttons find the weights.

Run after every training that writes checkpoints but never calls cotraffic select.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project root, not scripts/
TRAIN_DIR = ROOT / "results" / "training"
OUT_DIR = ROOT / "results" / "checkpoints"
MODELS_DIR = ROOT / "results" / "models"
REGISTRY_PATH = ROOT / "results" / "models.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register_local_mirrors(total: int, info: dict, net: str) -> None:
    if not net:
        return
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry: dict = {"models": {}}
    if REGISTRY_PATH.is_file():
        with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
            registry = json.load(fh)

    models: dict[str, list] = registry.setdefault("models", {})
    for seed in ("1", "2"):
        cid = f"generalist|{net}|{seed}"
        ckpt = TRAIN_DIR / "generalist" / net / seed / "checkpoints" / f"model_{total}_steps.zip"
        sidecar_path = ckpt.with_suffix(".json")
        if not ckpt.is_file() or not sidecar_path.is_file():
            continue
        sha = _sha256(ckpt)
        existing = next(
            (v for versions in models.values() for v in versions if v.get("sha256") == sha),
            None,
        )
        if existing:
            print(f"already registered: {existing.get('runName')} v{existing.get('version')} (sha {sha[:10]}..)")
            continue
        versions = models.setdefault("generalist", [])
        version = max((int(v.get("version", 0)) for v in versions), default=0) + 1
        artifact_dir = MODELS_DIR / uuid.uuid4().hex
        artifact_dir.mkdir(parents=True, exist_ok=True)
        dst = artifact_dir / "weights.zip"
        dst.write_bytes(ckpt.read_bytes())
        dst.with_suffix(".json").write_text(sidecar_path.read_text(encoding="utf-8"), encoding="utf-8")
        versions.append({
            "version": version,
            "runId": cid,
            "runName": "generalist",
            "network": net,
            "checkpoint": f"results/models/{artifact_dir.name}/weights.zip",
            "sha256": sha,
            "bytes": ckpt.stat().st_size,
            "trainingSeed": int(seed),
            "timesteps": total,
            "algorithm": "ppo",
            "method": "generalist",
            "recipeHash": info.get("recipe_hash", ""),
            "recipe": info.get("config", {}),
            "available": True,
            "promoted": False,
            "notes": "mirrored by sync_training_checkpoints.py (no live register endpoint)",
            "createdAt": UTC().now().isoformat(),
        })
        print(f"registered local mirror: generalist v{version} ({cid})")
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    os.replace(tmp, REGISTRY_PATH)
    print(f"models.json: {sum(len(v) for v in models.values())} registered versions")


def main() -> None:
    runs = 0
    seen_networks: dict[str, dict] = {}  # net -> info (last seen for registration)
    for seed_folder in sorted(TRAIN_DIR.glob("*/*/seed*/checkpoints")):
        parent = seed_folder.parent
        try:
            agent = parent.parent.parent.name  # recipe
            net = parent.parent.name           # network
            seed = int(parent.name.removeprefix("seed"))
        except Exception:
            continue

        info_path = parent / "run_info.json"
        if not info_path.is_file():
            continue
        with info_path.open("r", encoding="utf-8") as fh:
            info = json.load(fh)
        total = int(info.get("total_timesteps", 0))
        seen_networks[net] = info

        ckpts = sorted(
            [
                (int(p.name.removeprefix("model_").removesuffix("_steps.zip")), p)
                for p in seed_folder.glob("model_*_steps.zip")
            ],
            key=lambda x: x[0],
        )
        if not ckpts:
            continue

        # Pick the checkpoint whose steps come closest to (but <=) total_timesteps,
        # then write a sidecar at model_{chosen_steps}_steps.json so
        # _training_candidates() finds it.
        chosen_steps, chosen = None, None
        for steps, p in ckpts:
            if steps <= total:
                chosen_steps, chosen = steps, p
        if chosen is None:
            chosen_steps, chosen = ckpts[-1]

        sidecar_name = f"model_{chosen_steps}_steps.json"
        sidecar = chosen.with_name(sidecar_name)
        if not sidecar.is_file():
            sidecar_config = info.get("config", {})
            with sidecar.open("w", encoding="utf-8") as fh:
                json.dump({
                    "agent": agent,
                    "network": net,
                    "training_seed": seed,
                    "selected_checkpoint": chosen.name,
                    "selected_steps": chosen_steps,
                    "selected": True,
                    "config": sidecar_config,
                    "recipe_hash": info.get("recipe_hash", ""),
                    "total_timesteps": total,
                }, fh, indent=2)

        # _training_candidates() reads total_timesteps from run_info.json and then
        # expects checkpoints/model_{total_timesteps}_steps.zip + .json side by side.
        # Write that exact pair (copy the chosen weights; sidecar describes total).
        official_name = f"model_{total}_steps.zip"
        official = chosen.with_name(official_name)
        official.write_bytes(chosen.read_bytes())
        official_sidecar = official.with_suffix(".json")
        official_sidecar.write_text(
            json.dumps({
                "agent": agent,
                "network": net,
                "training_seed": seed,
                "selected_checkpoint": official_name,
                "selected_steps": total,
                "selected": True,
                "config": info.get("config", {}),
                "recipe_hash": info.get("recipe_hash", ""),
                "total_timesteps": total,
                "scores": {},
            }, indent=2),
            encoding="utf-8",
        )

        out = OUT_DIR / agent / net / f"seed{seed}.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chosen, out)
        with out.with_suffix(".json").open("w", encoding="utf-8") as fh:
            json.dump({
                "agent": agent,
                "network": net,
                "training_seed": seed,
                "selected_checkpoint": chosen.name,
                "selected_steps": chosen_steps,
                "selected": True,
                "config": info.get("config", {}),
                "recipe_hash": info.get("recipe_hash", ""),
                "total_timesteps": total,
                "scores": {},
            }, fh, indent=2)

        runs += 1
        print(f"synced {agent}|{net}|seed{seed} -> {out.name} (chosen {chosen_steps} <= {total})")

    print(f"done: synced {runs} checkpoint(s)")
    if runs:
        for net, info in seen_networks.items():
            total = int(info.get("total_timesteps", 0))
            _register_local_mirrors(total, info, net)


if __name__ == "__main__":
    main()
