"""Approach inflow counts for short-term forecasting.

Induction loops are placed at the upstream end of every lane entering a signalised
intersection. We run full evaluation-length episodes under Max-Pressure control on
seeds reserved for this purpose (6000+) and aggregate the loop counts per approach and
per minute: one row = (run, intersection, side, minute, vehicles).
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from cotraffic import config
from cotraffic.paths import RESULTS_DIR
from cotraffic.seeds import FORECAST_SEED_BASE

DATA_DIR = RESULTS_DIR / "forecasting"


def detector_file(env_net: str, out_file: Path, xml_out: Path) -> list[tuple[str, str, str]]:
    """Write induction loops on every incoming lane; returns (loop, tls, side) triples."""
    from cotraffic.networks.build import ensure_network
    from cotraffic.networks.topology import load_net, tls_geometry

    net_file = ensure_network(env_net)
    net = load_net(str(net_file))
    geometry = tls_geometry(net_file)
    loops, lines = [], ["<additional>"]
    for tid, geo in geometry.items():
        for edge_id in geo.incoming_edges:
            edge = net.getEdge(edge_id)
            for lane in edge.getLanes():
                if not lane.allows("passenger"):
                    continue
                loop = f"in_{tid}_{lane.getID()}"
                pos = min(5.0, lane.getLength() / 2)
                lines.append(
                    f'    <inductionLoop id="{loop}" lane="{lane.getID()}" pos="{pos:.1f}" '
                    f'period="60" file="{xml_out.as_posix()}"/>'
                )
                loops.append((loop, tid, geo.edge_side[edge_id]))
    lines.append("</additional>")
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return loops


def _record(args: tuple[str, str, int] | tuple[str, str, int, str]) -> pd.DataFrame:
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.controllers.classical import MaxPressure
    from cotraffic.envs.episodes import evaluation_episode
    from cotraffic.envs.traffic_env import CoTrafficEnv

    network, demand, seed, mode = (*args, "evaluation")[:4]
    work = DATA_DIR / "tmp" / f"{network}_{demand}_s{seed}"
    work.mkdir(parents=True, exist_ok=True)
    loops_xml = work / "loops.xml"
    loops = detector_file(network, work / "loops.add.xml", loops_xml)
    episode = evaluation_episode(
        network, demand, [], seed, ssm=False, additional=[work / "loops.add.xml"], mode=mode
    )
    env = CoTrafficEnv(network, lambda rng: episode, controlled=True, compute_observations=False)
    controller = MaxPressure()
    try:
        obs, _ = env.reset(seed=seed)
        while env.agents:
            obs, *_ = env.step(controller.act(env, obs))
    finally:
        env.close()
    owner = {loop: (tid, side) for loop, tid, side in loops}
    counts: dict[tuple[str, str, int], float] = defaultdict(float)
    for _, el in ET.iterparse(loops_xml):
        if el.tag == "interval":
            tid, side = owner[el.get("id")]
            minute = int(float(el.get("begin")) // 60)
            counts[(tid, side, minute)] += float(el.get("nVehEntered", el.get("nVehContrib", 0)))
        el.clear()
    rows = [
        {
            "network": network,
            "demand": demand,
            "seed": seed,
            "tls": t,
            "side": s,
            "minute": m,
            "vehicles": v,
            "demand_end_minute": episode.measure_to / 60.0,
        }
        for (t, s, m), v in sorted(counts.items())
    ]
    return pd.DataFrame(rows)


def build_dataset(
    network: str = "grid3x3",
    seeds_per_level: int = 4,
    jobs: int = 2,
    mode: str = "evaluation",
    out_dir: Path = DATA_DIR,
) -> Path:
    levels = config.load_protocol()["training"]["demand_levels"]
    tasks = [
        (network, level, FORECAST_SEED_BASE + k, mode)
        for level in levels
        for k in range(seeds_per_level)
    ]
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        frames = list(pool.map(_record, tasks))
    df = pd.concat(frames, ignore_index=True)
    out = out_dir / f"inflow_{network}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out
