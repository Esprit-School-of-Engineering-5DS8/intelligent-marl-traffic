"""Study "bigcity" (exploratory, STOPPED): does the frozen candidate generalise to a large city?

    python scripts/bigcity.py lights                       # the lights and what the agents drive
    python scripts/bigcity.py calibrate [--scales ...]     # demand with FT and MP, seed 1000
    python scripts/bigcity.py check                        # compatibility, seed 1000
    python scripts/bigcity.py demo --scale 0.5 --seeds 0 1 2   # every controller, LLM included

Stopped by the team on 2026-10-31 before any test seed (docs/FAILURES.md, F-016): the
Barcelona import blocks under every controller, fixed time included, and on Paris
Max-Pressure collapses while fixed time works. Kept as documented attempts; nothing here is
an evaluation result. Resumed on 2026-11-02 at the team's request as an exploratory
demonstration (``demo``): reduced demand (the planned demand blocks even fixed time), every
controller including the candidate with the LLM strategist, never part of the
preregistered results. Network: BIGCITY_NETWORK (barcelona, or paris), never trained on,
driven by the COOP-FULL models of real_district (same observation format). Everything goes
to results/bigcity/.

The lights the policies cannot read (one green phase, or more than the 3 phases of the
models) are taken out of the set of agents, here and nowhere else: the function that lists
the lights of a network is wrapped in this script's processes, so that the common
environment is not modified. Those lights keep their SUMO program (the one netconvert built
from OpenStreetMap) for every method; neighbour links that point to them are dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # inherited by the workers

import pandas as pd  # noqa: E402

import cotraffic.envs.traffic_env as traffic_env  # noqa: E402
import cotraffic.networks.topology as topology  # noqa: E402
from cotraffic import config  # noqa: E402
from cotraffic.envs.intersection import green_states  # noqa: E402
from cotraffic.paths import CHECKPOINTS_DIR, REPO_ROOT, RESULTS_DIR  # noqa: E402

NETWORK = os.environ.get("BIGCITY_NETWORK", "barcelona")  # inherited by the workers
MODELS_FROM = "real_district"  # the trained network whose observation format it shares
OUT = RESULTS_DIR / "bigcity"
NET_FILE = REPO_ROOT / "sumo_files" / NETWORK / f"{NETWORK}.net.xml"
SCENARIOS = ["normal", "emergency"]
LLM_METHOD = "hybrid_h2_llmstrat"


# ---------------------------------------------------------------- the lights
def light_table(net_file: Path = NET_FILE) -> pd.DataFrame:
    """Every light: green phases (as the environment counts them), incoming approaches and
    their lanes, and whether the agents drive it (2 to max_phases phases)."""
    text = net_file.read_text(encoding="utf-8")
    max_phases = int(config.load("networks", NETWORK)["padding"]["max_phases"])
    lanes: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for m in re.finditer(r"<connection ([^>]*)/>", text):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if "tl" in a and not a["from"].startswith(":"):
            lanes[a["tl"]][a["from"]].add(a["fromLane"])
    rows = []
    for tid, body in re.findall(r'<tlLogic id="([^"]+)"[^>]*>(.*?)</tlLogic>', text, re.S):
        phases = len(green_states(re.findall(r'state="([^"]+)"', body)))
        approaches = lanes.get(tid, {})
        widest = max((len(v) for v in approaches.values()), default=0)
        rows.append(
            {
                "light": tid,
                "phases": phases,
                "approaches": len(approaches),
                "lanes": sum(len(v) for v in approaches.values()),
                "widest_approach": widest,
                "driven": 2 <= phases <= max_phases,
                "wide": widest > 3,
            }
        )
    return pd.DataFrame(rows).sort_values("light").reset_index(drop=True)


DRIVEN = set(light_table().query("driven").light) if NET_FILE.is_file() else set()
_tls_geometry = topology.tls_geometry


def driven_geometry(net_file, max_distance: float = 500.0):
    """tls_geometry of the common code, limited on this network to the lights the agents
    drive; neighbour links to the other lights are dropped."""
    geo = _tls_geometry(net_file, max_distance)
    if Path(net_file).resolve() != NET_FILE.resolve():
        return geo
    geo = {tid: g for tid, g in geo.items() if tid in DRIVEN}
    for g in geo.values():
        g.neighbours = {s: link for s, link in g.neighbours.items() if link.tls_id in DRIVEN}
    return geo


traffic_env.tls_geometry = driven_geometry  # this script's processes only


def cmd_lights(_args) -> None:
    t = light_table()
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / f"{NETWORK}_lights.csv", index=False)
    driven = t[t.driven]
    summary = {
        "lights": int(len(t)),
        "driven": int(len(driven)),
        "driven_share_lights_pct": round(100 * len(driven) / len(t), 1),
        "driven_share_lanes_pct": round(100 * driven.lanes.sum() / t.lanes.sum(), 1),
        "phases": {str(k): int(v) for k, v in t.phases.value_counts().sort_index().items()},
        "wide_lights": int(t.wide.sum()),
        "wide_driven_lights": int(driven.wide.sum()),
        "not_driven": t[~t.driven].light.tolist(),
    }
    (OUT / f"{NETWORK}_lights.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "not_driven"}, indent=1))


# ---------------------------------------------------------------- episodes
def controller(method: str, run: int, scale: float = 1.0):
    from cotraffic.controllers.registry import make_controller

    if method == "ft":  # Webster plan computed for the demand actually played
        return make_controller("ft", scale=scale), None
    if method in ("mp", "ev_rule_mp"):
        return make_controller(method), None
    ckpt = CHECKPOINTS_DIR / "coop_full" / MODELS_FROM / f"seed{run}.zip"
    if method == LLM_METHOD:  # the candidate with the LLM strategist (llm/strategist.py)
        from cotraffic.llm.client import Ollama
        from cotraffic.llm.settings import load_settings
        from cotraffic.llm.strategist import LlmStrategist, LlmStrategyPolicy, StrategistPrompt

        cfg = load_settings()
        strategist = LlmStrategist(Ollama(cfg.model, cfg.options), StrategistPrompt.load())
        return LlmStrategyPolicy(make_controller("coop_full", ckpt), strategist, 4.0, method), ckpt
    return make_controller(method, ckpt), ckpt


class LightProbe:
    """Per light, every 5 s: vehicles halting on its incoming lanes, and phase changes."""

    def __init__(self) -> None:
        self.halting: dict[str, float] = defaultdict(float)
        self.changes: dict[str, int] = defaultdict(int)
        self.samples = 0
        self._phase: dict[str, int] = {}

    def __call__(self, env, now: float) -> None:
        if int(now) % 5:
            return
        self.samples += 1
        lane = env.conn.lane
        for tid, inter in env.intersections.items():
            self.halting[tid] += sum(lane.getLastStepHaltingNumber(ln) for ln in inter.in_lanes)
            if self._phase.get(tid, inter.phase) != inter.phase:
                self.changes[tid] += 1
            self._phase[tid] = inter.phase


def episode(task: tuple) -> dict:
    """One episode: (method, scenario, seed, run, scale, mode, folder)."""
    from cotraffic.evaluation.runner import run_episode

    method, scenario, seed, run, scale, mode, folder = task
    ctrl, ckpt = controller(method, run, scale)
    probe = LightProbe()
    hooks = ctrl.step_hooks()
    ctrl.step_hooks = lambda: [*hooks, probe]  # this episode's controller only
    tag = "-".join(x for x in (f"t{run}" if ckpt else "", f"x{scale:g}" if scale != 1 else "") if x)
    row = run_episode(method, NETWORK, "peak", [scenario], seed, checkpoint=ckpt, ssm=False,
                      tag=tag, raw_dir=OUT / folder / "raw", logs_dir=OUT / folder / "logs",
                      controller=ctrl, scale=scale, mode=mode)  # fmt: skip
    row.update({"train_run": run, "models_from": MODELS_FROM, "agents": len(DRIVEN),
                "sumo_backend": "libsumo"})  # fmt: skip
    if hasattr(ctrl, "summary"):
        row.update(ctrl.summary())
    if hasattr(ctrl, "call_log"):  # every call of the LLM strategist
        calls = OUT / folder / "calls"
        calls.mkdir(parents=True, exist_ok=True)
        with (calls / f"{row['run_id']}.jsonl").open("w", encoding="utf-8") as f:
            for c in ctrl.call_log():
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    per_light = pd.DataFrame(
        {"light": sorted(probe.halting),
         "mean_halting": [probe.halting[t] / max(1, probe.samples) for t in sorted(probe.halting)],
         "phase_changes": [probe.changes[t] for t in sorted(probe.halting)]}
    )  # fmt: skip
    (OUT / folder / "lights").mkdir(parents=True, exist_ok=True)
    per_light.to_csv(OUT / folder / "lights" / f"{row['run_id']}.csv", index=False)
    pd.DataFrame([row]).to_csv(OUT / folder / "raw" / f"{row['run_id']}.csv", index=False)
    return row


def run_all(tasks: list[tuple], jobs: int) -> list[dict]:
    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for row in pool.map(episode, tasks):
            print(f"done {row['run_id']} ({row['sim_wall_time_s']:.0f} s)", flush=True)
            rows.append(row)
    return rows


COLUMNS = ["run_id", "vehicles", "mean_travel_time", "mean_waiting_time", "p95_waiting_time",
           "mean_insertion_backlog", "unfinished", "never_inserted", "teleports_total",
           "ev_count", "ev_delay", "ev_delays", "sim_wall_time_s"]  # fmt: skip


def cmd_calibrate(args) -> None:
    folder = "calibration" if args.mode == "evaluation" else f"calibration_{args.mode}"
    tasks = [(m, "normal", 1000, 0, s, args.mode, folder)
             for m in ("ft", "mp") for s in args.scales]  # fmt: skip
    rows = run_all(tasks, args.jobs)
    measured_h = float(config.load_protocol()[args.mode]["measure_s"]) / 3600
    table = pd.DataFrame(rows)[
        [c for c in COLUMNS if c not in ("ev_count", "ev_delay", "ev_delays")]
    ]
    table.insert(1, "veh_per_h", [round(r["vehicles"] / measured_h) for r in rows])
    table.to_csv(OUT / folder / "sweep.csv", index=False)
    print(table.round(1).to_string(index=False))


def cmd_check(args) -> None:
    methods = [("mp", 0), ("ev_rule_mp", 0)] + [
        (m, k) for m in ("coop_full", "hybrid_h2") for k in (1, 2, 3)
    ]
    tasks = [(m, s, 1000, k, 1.0, "evaluation", "check") for s in SCENARIOS for m, k in methods
             if not (m == "ev_rule_mp" and s == "normal")]  # fmt: skip
    rows = run_all(tasks, args.jobs)
    table = pd.DataFrame(rows)[COLUMNS]
    table.to_csv(OUT / "check" / "summary.csv", index=False)
    print(table.drop(columns="ev_delays").round(1).to_string(index=False))


DEMO_METHODS = [("ft", 0), ("mp", 0), ("ev_rule_mp", 0), ("coop_full", 1), ("hybrid_h2", 1),
                (LLM_METHOD, 1)]  # fmt: skip


def cmd_demo(args) -> None:
    """Every controller at a demand the network can carry (exploratory demonstration)."""
    tasks = [(m, s, seed, k, args.scale, "evaluation", "demo") for seed in args.seeds
             for s in SCENARIOS for m, k in DEMO_METHODS
             if not (m == "ev_rule_mp" and s == "normal")]  # fmt: skip
    # the LLM episodes first: the slowest, so that the pool ends together
    tasks.sort(key=lambda t: t[0] != LLM_METHOD)
    done = {p.stem for p in (OUT / "demo" / "raw").glob("*.csv")}
    rows = run_all([t for t in tasks if demo_id(t) not in done], args.jobs)
    print(pd.DataFrame(rows)[[c for c in COLUMNS if c != "ev_delays"]].round(1).to_string())


def demo_id(task: tuple) -> str:
    from cotraffic.evaluation.runner import run_id

    method, scenario, seed, run, scale, _, _ = task
    ckpt = method not in ("ft", "mp", "ev_rule_mp")
    tag = "-".join(x for x in (f"t{run}" if ckpt else "", f"x{scale:g}" if scale != 1 else "") if x)
    return run_id(method, NETWORK, [s for s in [scenario] if s != "normal"], "peak", seed, tag)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lights").set_defaults(func=cmd_lights)
    p = sub.add_parser("calibrate")
    p.add_argument("--scales", type=float, nargs="+", default=[0.6, 0.8, 1.0, 1.2])
    p.add_argument("--mode", default="evaluation", choices=["evaluation", "quick"])
    p.add_argument("--jobs", type=int, default=4)
    p.set_defaults(func=cmd_calibrate)
    p = sub.add_parser("check")
    p.add_argument("--jobs", type=int, default=4)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("demo")
    p.add_argument("--scale", type=float, default=0.5)
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_demo)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    args.func(args)


if __name__ == "__main__":
    main()
