"""What each environment reset simulates.

Seed ranges are disjoint by construction:

* test (evaluation) seeds: 0-999, chosen in the experiment configs
* validation seeds (checkpoint selection): 1000-1999
* training seeds: a fixed pool starting at 100000, shared by every variant so that
  all variants see the same training demand.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cotraffic import config
from cotraffic.demand.generator import DemandRequest, generate
from cotraffic.envs.simulation import Episode
from cotraffic.networks.build import ensure_network

ROUTE_KEYS = ("incident", "emergency", "pedestrians", "buses")
RUNTIME_KEYS = ("sensor_noise", "comm_dropout")
TRAINING_SEED_BASE = 100_000
VALIDATION_SEED_BASE = 1_000


def split_scenarios(names: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate scenarios that change the demand from those that act at run time."""
    route, runtime = [], []
    for name in names:
        cfg = config.load("scenarios", name)
        if any(k in cfg for k in ROUTE_KEYS):
            route.append(name)
        if any(k in cfg for k in RUNTIME_KEYS):
            runtime.append(name)
    return tuple(route), tuple(runtime)


class TrainingEpisodes:
    """Domain randomisation: a demand level and a demand seed drawn at every reset."""

    def __init__(
        self,
        network: str,
        demand_levels: Sequence[str],
        scenarios: Sequence[str] = (),
        episode_s: float = 3600.0,
        pool_size: int = 50,
    ):
        self.network = network
        self.levels = list(demand_levels)
        self.scenarios, _ = split_scenarios(scenarios)
        self.episode_s = float(episode_s)
        self.pool = [TRAINING_SEED_BASE + i for i in range(pool_size)]
        self.net_file = ensure_network(network)

    def __call__(self, rng: np.random.Generator) -> Episode:
        level = self.levels[int(rng.integers(len(self.levels)))]
        seed = self.pool[int(rng.integers(len(self.pool)))]
        bundle = generate(
            DemandRequest(self.network, level, self.scenarios, seed, 0.0, self.episode_s)
        )
        return Episode(
            self.net_file,
            bundle,
            end_time=self.episode_s,
            sumo_seed=seed,
            measure_from=0.0,
            measure_to=self.episode_s,
            info={"demand": level, "seed": seed, "scenarios": list(self.scenarios)},
        )


def evaluation_episode(
    network: str,
    demand: str,
    scenarios: Sequence[str],
    seed: int,
    output_dir: Path | None = None,
    ssm: bool = True,
    additional: Sequence[Path] = (),
    protocol: Mapping[str, Any] | None = None,
    quick: bool = False,
    scale: float = 1.0,
    mode: str = "evaluation",
) -> Episode:
    """Warm-up + measured window + cool-down, as defined in configs/protocol.yaml
    (section ``mode``: ``evaluation``, ``validation``; ``quick`` overrides it)."""
    protocol = protocol or config.load_protocol()
    ev = protocol["quick" if quick else mode]
    warmup, measure, cooldown = (float(ev[k]) for k in ("warmup_s", "measure_s", "cooldown_s"))
    route_scenarios, _ = split_scenarios(scenarios)
    bundle = generate(DemandRequest(network, demand, route_scenarios, seed, warmup, measure, scale))
    return Episode(
        ensure_network(network),
        bundle,
        end_time=warmup + measure + cooldown,
        sumo_seed=seed,
        measure_from=warmup,
        measure_to=warmup + measure,
        output_dir=output_dir,
        ssm=ssm,
        additional=tuple(additional),
        info={"demand": demand, "seed": seed, "scenarios": list(scenarios), "quick": quick},
    )
