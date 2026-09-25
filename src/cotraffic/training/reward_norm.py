"""Reward normalisation constants, estimated from baseline runs.

Each reward term has its own unit (vehicle-seconds of waiting, milligrams of CO2,
seconds of emergency-vehicle waiting, pedestrian-seconds). We run Max-Pressure on
training demand, record every raw term of every agent decision, and choose scales that
bring each term to order 1:

* waiting change: standard deviation (the term is centred, its sign carries the signal);
* queue, pressure and CO2: mean per decision (they are never negative);
* emergency-vehicle and pedestrian waiting: mean of the non-zero values - these terms
  are zero most of the time, and their scale should reflect a typical event, not the
  long quiet periods between events.

The constants are written to ``configs/reward_norm/<network>.yaml`` and read by the
environment, so every variant trained on a network uses the same scales.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import yaml

from cotraffic import config
from cotraffic.controllers.classical import MaxPressure
from cotraffic.envs.episodes import TRAINING_SEED_BASE, unsupported
from cotraffic.envs.simulation import Episode
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.paths import CONFIG_DIR

TERMS = ("wait", "queue", "pressure", "co2", "ev", "ped")


def calibrate_rewards(
    network: str, demands: tuple[str, ...] = ("medium", "peak"), episode_s: float = 3600.0
) -> Path:
    from cotraffic.demand.generator import DemandRequest, generate
    from cotraffic.networks.build import ensure_network

    agent = config.load_agent("coop_full")
    excluded = unsupported(network)
    scenarios = tuple(sc for sc in agent["training"]["scenarios"] if sc not in excluded)
    samples: dict[str, list[float]] = {t: [] for t in TERMS}
    runs = []
    for i, demand in enumerate(demands):
        seed = TRAINING_SEED_BASE + i
        bundle = generate(DemandRequest(network, demand, scenarios, seed, 0.0, episode_s))
        episode = Episode(ensure_network(network), bundle, end_time=episode_s, sumo_seed=seed)
        env = CoTrafficEnv(network, lambda rng, ep=episode: ep, agent)
        controller = MaxPressure()
        try:
            obs, _ = env.reset(seed=seed)
            while env.agents:
                obs, _, _, _, infos = env.step(controller.act(env, obs))
                for info in infos.values():
                    for term in TERMS:
                        samples[term].append(float(info["raw"][term]))
        finally:
            env.close()
        runs.append({"demand": demand, "seed": seed, "scenarios": list(scenarios)})

    arrays = {t: np.asarray(v) for t, v in samples.items()}
    nonzero = {t: arrays[t][arrays[t] > 0] for t in ("ev", "ped")}
    norm = {
        "wait": float(arrays["wait"].std()),
        "queue": float(arrays["queue"].mean()),
        "pressure": float(arrays["pressure"].mean()),
        "co2": float(arrays["co2"].mean()),
        "ev": float(nonzero["ev"].mean()) if nonzero["ev"].size else 1.0,
        "ped": float(nonzero["ped"].mean()) if nonzero["ped"].size else 1.0,
    }
    out = CONFIG_DIR / "reward_norm" / f"{network}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "norm": {k: round(v, 4) for k, v in norm.items()},
        "estimated_with": {
            "controller": "mp",
            "runs": runs,
            "agent_decisions": int(arrays["wait"].size),
            "nonzero_ev_decisions": int(nonzero["ev"].size),
            "nonzero_ped_decisions": int(nonzero["ped"].size),
            "date": time.strftime("%Y-%m-%d"),
        },
    }
    header = "# Written by `python -m cotraffic calibrate`; do not edit by hand.\n"
    out.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out
