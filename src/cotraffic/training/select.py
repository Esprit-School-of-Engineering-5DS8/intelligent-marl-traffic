"""Choose the checkpoint of a training run to evaluate, on validation seeds only.

The last ``validation.last_checkpoints`` checkpoints of a run are evaluated on the
validation seeds (1000+) and demands of the agent config; the one with the lowest mean
travel time is copied to ``results/checkpoints/<agent>/<network>/seed<k>.zip`` with a
JSON record of every score. Evaluation seeds are never used here.
"""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from cotraffic import config
from cotraffic.paths import CHECKPOINTS_DIR, TRAINING_DIR
from cotraffic.seeds import VALIDATION_SEEDS, check_seeds
from cotraffic.training.train import list_checkpoints, run_dir


def _validate(args: tuple[str, str, str, int, str, int]) -> tuple[int, str, int, float]:
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.evaluation.runner import run_episode

    agent, network, demand, seed, checkpoint, steps = args
    folder = Path(checkpoint).parent.parent
    row = run_episode(
        agent,
        network,
        demand,
        [],
        seed,
        checkpoint=Path(checkpoint),
        ssm=False,
        mode="validation",
        tag=f"val{steps}",
        raw_dir=folder / "validation",
        logs_dir=folder / "validation_logs",
    )
    return steps, demand, seed, float(row["mean_travel_time"])


def select_checkpoint(agent: str, network: str, seed: int, jobs: int = 2) -> Path:
    cfg = config.load_agent(agent)
    val = cfg["validation"]
    check_seeds(val["seeds"], VALIDATION_SEEDS, "validation")
    folder = run_dir(agent, network, seed)
    ckpts = list_checkpoints(folder / "checkpoints")[-int(val["last_checkpoints"]) :]
    if not ckpts:
        raise FileNotFoundError(f"no checkpoint in {folder / 'checkpoints'}")
    tasks = [
        (agent, network, d, int(s), str(p), steps)
        for steps, p in ckpts
        for d in val["demands"]
        for s in val["seeds"]
    ]
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(_validate, tasks))
    scores: dict[int, list[float]] = {}
    for steps, _demand, _seed, travel in results:
        scores.setdefault(steps, []).append(travel)
    best = min(scores, key=lambda k: np.mean(scores[k]))
    source = dict(ckpts)[best]
    out = CHECKPOINTS_DIR / agent / network / f"seed{seed}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, out)
    info_file = folder / "run_info.json"
    train_info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.is_file() else {}
    record = {
        "agent": agent,
        "network": network,
        "training_seed": seed,
        "selected_checkpoint": source.name,
        "selected_steps": best,
        "validation": {
            "seeds": val["seeds"],
            "demands": val["demands"],
            "metric": "mean_travel_time",
            "episode": "protocol.validation",
        },
        "scores": {
            str(k): {"mean_travel_time": float(np.mean(v)), "runs": v}
            for k, v in sorted(scores.items())
        },
        "train_wall_time_s": train_info.get("train_wall_time_s"),
        "total_timesteps": train_info.get("total_timesteps"),
        "config": cfg,
    }
    out.with_suffix(".json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return out


def trained_runs(
    agent: str | None = None, network: str | None = None
) -> list[tuple[str, str, int]]:
    """(agent, network, seed) of every training folder with checkpoints."""
    found = []
    for ckpt_dir in sorted(TRAINING_DIR.glob("*/*/seed*/checkpoints")):
        seed_dir = ckpt_dir.parent
        a, n = seed_dir.parent.parent.name, seed_dir.parent.name
        if (agent and a != agent) or (network and n != network) or not list_checkpoints(ckpt_dir):
            continue
        found.append((a, n, int(seed_dir.name.removeprefix("seed"))))
    return found


def validation_table(
    agents: list[str],
    baselines: list[str],
    network: str,
    seed: int = 1,
    val_seeds: tuple[int, ...] = (1000, 1001),
    jobs: int = 2,
) -> Path:
    """Final checkpoints of several variants and some baselines on validation episodes
    (used for design choices such as the reward definition, never for reporting)."""
    import pandas as pd

    from cotraffic.paths import RESULTS_DIR

    check_seeds(val_seeds, VALIDATION_SEEDS, "validation")
    demands = config.load_agent("base")["validation"]["demands"]
    tasks = []
    for agent in agents:
        steps, path = list_checkpoints(run_dir(agent, network, seed) / "checkpoints")[-1]
        tasks += [(agent, network, d, s, str(path), steps) for d in demands for s in val_seeds]
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        learned = list(pool.map(_validate, tasks))
        base = list(
            pool.map(
                _validate_baseline,
                [(m, network, d, s) for m in baselines for d in demands for s in val_seeds],
            )
        )
    rows = [
        {"method": t[0], "steps": r[0], "demand": r[1], "seed": r[2], "mean_travel_time": r[3]}
        for t, r in zip(tasks, learned, strict=True)
    ]
    rows += [
        {"method": m, "steps": 0, "demand": d, "seed": s, "mean_travel_time": v}
        for m, d, s, v in base
    ]
    out = RESULTS_DIR / "exploration" / f"{network}_validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if out.is_file():
        old = pd.read_csv(out)
        df = pd.concat([old[~old["method"].isin(df["method"])], df], ignore_index=True)
    df.to_csv(out, index=False)
    return out


def _validate_baseline(args: tuple[str, str, str, int]) -> tuple[str, str, int, float]:
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.evaluation.runner import run_episode
    from cotraffic.paths import RESULTS_DIR

    method, network, demand, seed = args
    work = RESULTS_DIR / "exploration" / "runs"
    row = run_episode(
        method,
        network,
        demand,
        [],
        seed,
        ssm=False,
        mode="validation",
        tag="val",
        raw_dir=work,
        logs_dir=work / "logs",
    )
    return method, demand, seed, float(row["mean_travel_time"])
