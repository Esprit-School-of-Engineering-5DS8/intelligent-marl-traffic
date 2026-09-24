"""Two sumo-gui windows side by side, same demand and events, two controllers.

Default: the real district at peak with emergency vehicles, EV-RULE (actuated control
with rule-based preemption) on the left and COOP-FULL on the right. Record the screen.

    python scripts/demo_side_by_side.py [--left ev_rule] [--right coop_full]
        [--checkpoint results/checkpoints/coop_full/real_district/seed1.zip]
        [--net real_district] [--demand peak] [--scenarios emergency] [--seed 3]
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path


def run(
    method: str,
    checkpoint: str | None,
    network: str,
    demand: str,
    scenarios: list[str],
    seed: int,
    x: int,
    delay: int,
) -> None:
    from cotraffic.controllers.registry import make_controller
    from cotraffic.envs.episodes import evaluation_episode, split_scenarios
    from cotraffic.envs.traffic_env import CoTrafficEnv

    controller = make_controller(method, Path(checkpoint) if checkpoint else None)
    episode = evaluation_episode(
        network,
        demand,
        scenarios,
        seed,
        ssm=False,
        additional=controller.additional_files(network, demand),
    )
    _, runtime = split_scenarios(scenarios)
    env = CoTrafficEnv(
        network,
        lambda rng: episode,
        controller.agent_cfg,
        controlled=controller.controlled,
        gui=True,
        runtime_scenarios=runtime,
        step_hooks=controller.step_hooks(),
        compute_observations=controller.needs_observations,
        sumo_options=["--window-pos", f"{x},30", "--window-size", "940,900", "--delay", str(delay)],
    )
    obs, _ = env.reset(seed=seed)
    controller.reset(env)
    while env.agents:
        obs, *_ = env.step(controller.act(env, obs))
    env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", default="ev_rule")
    parser.add_argument("--right", default="coop_full")
    parser.add_argument(
        "--checkpoint", default="results/checkpoints/coop_full/real_district/seed1.zip"
    )
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--scenarios", nargs="*", default=["emergency"])
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--delay", type=int, default=40, help="ms per simulation step")
    args = parser.parse_args()
    jobs = []
    for method, x in ((args.left, 0), (args.right, 960)):
        ckpt = args.checkpoint if method not in ("ft", "act", "mp", "ev_rule") else None
        p = mp.Process(
            target=run,
            args=(method, ckpt, args.net, args.demand, args.scenarios, args.seed, x, args.delay),
        )
        p.start()
        jobs.append(p)
    for p in jobs:
        p.join()


if __name__ == "__main__":
    main()
