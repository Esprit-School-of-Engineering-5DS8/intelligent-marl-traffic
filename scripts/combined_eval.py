"""The teammate's LLM team in our protocol, next to our methods: validation seed only.

    python scripts/combined_eval.py [--methods ...] [--networks ...] [--scenarios ...]
        [--demands ...] [--runs 1 2 3] [--betas 4 8 16] [--seed 1000] [--jobs 4]
        [--dry-run] [--summary-only]
    python scripts/combined_eval.py --probe          # latency of the team on this machine

Cells: grid4x4 and real_district x normal, emergency, incident x medium, peak (validation
episodes: 600 s warm-up, 1800 s measured, 300 s cool-down). Methods: ft, mp, ev_rule_mp,
coop_full, coop_full_llm (the same policy with our advisor, configs/llm.yaml), team_rules
and team_qwen (controllers/team.py), and COOP-FULL guided during emergencies
(controllers/combined.py) by the teammate's rules or by our EV-RULE, with a bias on its
logits (A', one run per beta) or by switching (B'). The methods built on COOP-FULL run with
each training run of ``--runs``; their gains are paired with COOP-FULL of the same run.
Episodes without a language model run in parallel; the episodes with one run alone, one
after the other: the latency of each call is measured and sets the delay before its answer
acts.

Rows go to results/exploration/combined/raw/ (never results/raw), every call to calls/,
the comparison to combined_summary.csv (gains: positive = better).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from cotraffic import config
from cotraffic.controllers.combined import GUIDES, EvRuleGuide, GuidedPolicy
from cotraffic.controllers.hybrid import (
    CongestionStrategy,
    HybridPolicy,
    PedRuleGuide,
    TeamRoleGuide,
)
from cotraffic.controllers.registry import make_controller
from cotraffic.controllers.team import TEAM_NUM_CTX, prompt_version
from cotraffic.evaluation.runner import run_episode, run_id
from cotraffic.llm.advised import AdvisedPolicy
from cotraffic.llm.client import Ollama
from cotraffic.llm.prompts import load
from cotraffic.llm.settings import load_settings
from cotraffic.llm.sources import llm_source
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TEST_SEEDS
from cotraffic.utils.io import git_commit, write_row

OUT = RESULTS_DIR / "exploration" / "combined"
METHODS = ["ft", "mp", "ev_rule_mp", "coop_full", "coop_full_llm", "team_rules", "team_qwen"]
# COOP-FULL guided during emergencies: method -> (guide, mode)
GUIDED = {
    "coop_full_team_bias": ("team", "bias"),
    "coop_full_team_switch": ("team", "switch"),
    "coop_full_evrule_bias": ("ev_rule", "bias"),
    "coop_full_evrule_switch": ("ev_rule", "switch"),
}
# phase A: COOP-FULL under a strategy, with pre-emption (controllers/hybrid.py)
HYBRID = {
    "hybrid_h1": "ppo/max_pressure by congestion (H1) + switch(EV-RULE)",
    "hybrid_h2": "ppo + logit_bias(max_pressure) (H2) + switch(EV-RULE)",
    "coop_full_tped_switch": "ppo + switch(team serve_ped rules, no LLM) + switch(EV-RULE)",
    "coop_full_pedrule_switch": "ppo + switch(PED-RULE) + switch(EV-RULE)",
}
ALL_METHODS = METHODS + ["ped_rule_mp"] + list(GUIDED) + list(HYBRID)
THRESHOLDS = OUT / "congestion_thresholds.json"  # H1, from --profile-congestion
WITH_LLM = {"coop_full_llm", "team_qwen"}
NETWORKS = ["grid4x4", "real_district"]
SCENARIOS = ["normal", "emergency", "incident"]
DEMANDS = ["medium", "peak"]
MECHANISM = {
    "ft": "fixed_time",
    "mp": "max_pressure",
    "ev_rule_mp": "max_pressure+ev_preemption",
    "coop_full": "ppo",
    "coop_full_llm": "ppo+llm_logit_bias",
    "team_rules": "max_pressure+team_directives(code rules, no LLM)",
    "team_qwen": "max_pressure+team_directives(local LLM)",
    "coop_full_team_bias": "ppo+logit_bias(team emergency rules, no LLM)",
    "coop_full_team_switch": "ppo+switch(team emergency rules, no LLM)",
    "coop_full_evrule_bias": "ppo+logit_bias(EV-RULE)",
    "coop_full_evrule_switch": "ppo+switch(EV-RULE)",
    "ped_rule_mp": "max_pressure+ped_rule",
    **HYBRID,
}
TEAM_SOURCE = "teammate's LLM team (controllers/llm_team/PROVENANCE.md)"
LOWER_IS_BETTER = ["mean_travel_time", "others_travel_time", "mean_waiting_time", "ev_delay"]


def checkpoint(network: str, run: int) -> Path:
    return CHECKPOINTS_DIR / "coop_full" / network / f"seed{run}.zip"


def on_coop_full(method: str) -> bool:
    return method.startswith(("coop_full", "hybrid"))


def tag_of(method: str, run: int, param: float | None) -> str:
    """t<run>, then -b<beta> (bias) or -q<quantile> (H1 threshold)."""
    if not on_coop_full(method):
        return ""
    prefix = "q" if method == "hybrid_h1" else "b"
    return f"t{run}" + (f"-{prefix}{param:g}" if param is not None else "")


def rid_of(task: tuple) -> str:
    method, network, scenario, demand, seed, run, param = task
    scenarios = [s for s in [scenario] if s != "normal"]
    return run_id(method, network, scenarios, demand, seed, tag_of(method, run, param))


def run_task(task: tuple) -> dict:
    method, network, scenario, demand, seed, run, param = task
    settings = load_settings()
    rid = rid_of(task)
    calls_dir = OUT / "calls"
    calls_dir.mkdir(parents=True, exist_ok=True)
    extra: dict = {"mechanism": MECHANISM[method]}
    ckpt = checkpoint(network, run) if on_coop_full(method) else None
    if ckpt is not None:
        extra["train_run"] = run
    controller = None
    if method == "coop_full_llm":
        cfg = settings.advisor
        source, label = llm_source(
            settings.model, settings.technique, settings.options, settings.prompt_version
        )
        controller = AdvisedPolicy(make_controller("coop_full", ckpt), source, cfg)
        info = Ollama(settings.model, settings.options).fingerprint()
        extra.update(
            {
                "llm_model": settings.model,
                "llm_digest": info.get("digest", ""),
                "llm_quantization": info.get("quantization", ""),
                "prompt": load(settings.prompt_version, settings.technique).id,
                "technique": label,
                "beta": cfg.beta,
                "period_s": cfg.period_s,
                "latency_mode": cfg.latency,
                **{f"opt_{k}": v for k, v in asdict(settings.options).items()},
            }
        )
    elif method in GUIDED:
        guide, mode = GUIDED[method]
        controller = GuidedPolicy(make_controller("coop_full", ckpt), GUIDES[guide](), mode, param)
        if guide == "team":
            extra["source"] = TEAM_SOURCE
    elif method in HYBRID:
        base = make_controller("coop_full", ckpt)
        if method == "hybrid_h1":
            threshold = json.loads(THRESHOLDS.read_text(encoding="utf-8"))[network][f"q{param:g}"]
            controller = HybridPolicy(base, CongestionStrategy(threshold), ev_guide=EvRuleGuide())
            extra["quantile"] = param
        elif method == "hybrid_h2":
            controller = HybridPolicy(base, mp_beta=param, ev_guide=EvRuleGuide())
        elif method == "coop_full_tped_switch":
            ped = TeamRoleGuide(("pedestrian",))
            controller = HybridPolicy(base, ped_guide=ped, ev_guide=EvRuleGuide())
            extra["source"] = TEAM_SOURCE
        else:
            controller = HybridPolicy(base, ped_guide=PedRuleGuide(), ev_guide=EvRuleGuide())
    elif method in ("team_rules", "team_qwen"):
        log = calls_dir / f"{rid}.jsonl"
        log.unlink(missing_ok=True)  # the team's logger appends
        controller = make_controller(method, log_path=str(log))
        extra.update({"source": TEAM_SOURCE, "prompt": prompt_version()})
        if method == "team_qwen":
            info = Ollama(settings.model, controller.options).fingerprint()
            extra.update(
                {
                    "llm_model": settings.model,
                    "llm_digest": info.get("digest", ""),
                    "llm_quantization": info.get("quantization", ""),
                    **{f"opt_{k}": v for k, v in asdict(controller.options).items()},
                }
            )
    row = run_episode(
        method,
        network,
        demand,
        [scenario],
        seed,
        checkpoint=ckpt,
        tag=tag_of(method, run, param),
        raw_dir=OUT / "raw",
        logs_dir=OUT / "logs",
        controller=controller,
        mode="validation",
    )
    if method == "coop_full_llm":
        extra.update(controller.summary())
        with (calls_dir / f"{rid}.jsonl").open("w", encoding="utf-8") as f:
            for c in controller.calls:
                f.write(json.dumps(asdict(c), default=str) + "\n")
    elif method in GUIDED or method in HYBRID:
        extra.update(controller.summary())
    elif controller is not None and hasattr(controller, "metrics"):
        extra.update(controller.metrics())
    row.update(extra)
    write_row(OUT / "raw" / f"{rid}.csv", row)
    return row


def others_travel_time(r: dict) -> float:
    """Mean travel time of the vehicles other than the emergency vehicles."""
    n, k = float(r.get("vehicles", 0) or 0), float(r.get("ev_count", 0) or 0)
    if pd.isna(k) or k == 0:
        return float(r["mean_travel_time"])
    return (n * float(r["mean_travel_time"]) - k * float(r["ev_travel_time"])) / (n - k)


def train_run(r: dict) -> int:
    """Training run of a method built on COOP-FULL (0 for the others), from its variant."""
    match = re.match(r"t(\d+)", str(r.get("variant", "")))
    return int(match.group(1)) if match and on_coop_full(r["method"]) else 0


def summarise() -> pd.DataFrame:
    rows = [pd.read_csv(p).iloc[0].to_dict() for p in sorted((OUT / "raw").glob("*.csv"))]
    if not rows:
        return pd.DataFrame()
    for r in rows:
        r["others_travel_time"] = others_travel_time(r)
        r["train_run"] = train_run(r)
    df = pd.DataFrame(rows)
    out = []
    for (network, scenario, demand), cell in df.groupby(["network", "scenario", "demand"]):
        mp = cell[cell.method == "mp"]
        for r in cell.to_dict("records"):
            # COOP-FULL of the same training run: the gain of a guide is paired
            coop = cell[(cell.method == "coop_full") & (cell.train_run == max(r["train_run"], 1))]
            line = {
                "network": network,
                "scenario": scenario,
                "demand": demand,
                "method": r["method"],
                "variant": r["variant"],
                "train_run": r["train_run"],
            }
            for m in LOWER_IS_BETTER:
                value = r.get(m, float("nan"))
                line[m] = round(value, 2) if pd.notna(value) else None
                for ref, rd in (("mp", mp), ("coop_full", coop)):  # positive = better
                    if rd.empty or m not in rd or pd.isna(value) or pd.isna(rd[m].iloc[0]):
                        continue
                    base = float(rd[m].iloc[0])
                    line[f"gain_{m}_vs_{ref}_%"] = round(100 * (base - value) / max(base, 1e-9), 2)
            for k in (
                "ev_count",
                "ev_delays",
                "guided_decisions",
                "changed_decisions",
                "llm_changed_decisions",
                "teleported_vehicles",
                "unfinished",
            ):
                line[k] = r.get(k)
            out.append(line)
    order = {m: k for k, m in enumerate(ALL_METHODS)}
    table = pd.DataFrame(out)
    table["_o"] = table.method.map(order)
    keys = ["network", "scenario", "demand", "_o", "train_run", "variant"]
    return table.sort_values(keys).drop(columns="_o")


def probe(networks: list[str], seed: int) -> None:
    """Latency of the team with the local model on real snapshots (no row is written)."""
    from cotraffic.controllers.classical import MaxPressure
    from cotraffic.llm.rollout import EpisodeSpec, make_env

    for network in networks:
        team = make_controller("team_qwen")
        env = make_env(EpisodeSpec(network, "peak", ["emergency"], seed), team.agent_cfg)
        try:
            obs, _ = env.reset(seed=seed)
            mp = MaxPressure()
            mp.reset(env)
            t0 = time.perf_counter()
            while env.now < 1200:  # Max-Pressure through the warm-up: queues are formed
                obs, *_ = env.step(mp.act(env, obs))
            mp_pace = (time.perf_counter() - t0) / env.now
            team.reset(env)
            start, t0 = env.now, time.perf_counter()
            while env.now < start + 240:
                obs, *_ = env.step(team.act(env, obs))
            wall = time.perf_counter() - t0
            m = team.metrics()
        finally:
            env.close()
        print(
            f"{network}: {m.get('llm_team_calls', 0)} calls in 240 s simulated, wall {wall:.0f} s; "
            f"latency mean {m.get('llm_team_latency_mean_s', 0)} s, "
            f"p90 {m.get('llm_team_latency_p90_s', 0)} s; tokens in "
            f"{m.get('llm_team_tokens_in', 0)}, out {m.get('llm_team_tokens_out', 0)}; "
            f"fallbacks {m.get('llm_team_fallbacks', 0)}; Max-Pressure pace "
            f"{1000 * mp_pace:.1f} ms per simulated second; num_ctx {TEAM_NUM_CTX}"
        )


def tasks_for(args) -> list[tuple]:
    out = []
    for n in args.networks:
        for s in args.scenarios:
            for d in args.demands:
                for m in args.methods:
                    runs = args.runs if on_coop_full(m) else [0]
                    out += [(m, n, s, d, args.seed, k, p) for k in runs for p in params(m, args)]
    return out


def params(method: str, args) -> list:
    """The swept parameter of a method: beta of a bias guide or of H2, quantile of H1."""
    if GUIDED.get(method, ("", ""))[1] == "bias":
        return args.betas
    if method == "hybrid_h1":
        return args.h1_quantiles
    if method == "hybrid_h2":
        return args.h2_betas
    return [None]


def congestion_samples(task: tuple) -> np.ndarray:
    """Neighbourhood congestion of every junction at every decision of the measured window,
    under COOP-FULL (training run 1) in the normal scenario."""
    from cotraffic.llm.rollout import EpisodeSpec, make_env

    network, demand, seed = task
    timing = config.load_protocol()["validation"]
    begin = float(timing["warmup_s"])
    end = begin + float(timing["measure_s"])
    base = make_controller("coop_full", checkpoint(network, 1))
    env = make_env(EpisodeSpec(network, demand, [], seed), base.agent_cfg)
    probe_strategy = CongestionStrategy(threshold=float("inf"))
    values: list[float] = []
    try:
        obs, _ = env.reset(seed=seed)
        base.reset(env)
        probe_strategy.reset(env)
        while env.now < end:
            congestion = probe_strategy.observe(env)
            if env.now >= begin:
                values += list(congestion.values())
            obs, *_ = env.step(base.act(env, obs))
    finally:
        env.close()
    return np.array(values)


def profile_congestion(networks: list[str], demands: list[str], seed: int, jobs: int) -> None:
    """The thresholds of H1: quantiles 50, 75, 90 and 95 % of the congestion under COOP-FULL,
    per network, pooled over the demands (validation seed only)."""
    tasks = [(n, d, seed) for n in networks for d in demands]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        samples = dict(zip(tasks, pool.map(congestion_samples, tasks), strict=True))
    out = {}
    for n in networks:
        values = np.concatenate([v for (net, _, _), v in samples.items() if net == n])
        out[n] = {f"q{q}": round(float(np.quantile(values, q / 100)), 4) for q in (50, 75, 90, 95)}
        out[n]["samples"] = int(values.size)
        out[n]["source"] = (
            f"coop_full t1, normal, demands {'+'.join(demands)}, seed {seed}, measured window"
        )
    THRESHOLDS.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLDS.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--methods", nargs="+", default=METHODS, choices=ALL_METHODS)
    parser.add_argument("--networks", nargs="+", default=NETWORKS)
    parser.add_argument("--scenarios", nargs="+", default=SCENARIOS)
    parser.add_argument("--demands", nargs="+", default=DEMANDS)
    parser.add_argument("--runs", nargs="+", type=int, default=[1], help="COOP-FULL runs")
    parser.add_argument("--betas", nargs="+", type=float, default=[4.0], help="bias guides")
    parser.add_argument("--h1-quantiles", nargs="+", type=float, default=[50, 75, 90, 95])
    parser.add_argument("--h2-betas", nargs="+", type=float, default=[1.0, 2.0, 4.0])
    parser.add_argument("--profile-congestion", action="store_true", help="thresholds of H1")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--jobs", type=int, default=4, help="workers for episodes without LLM")
    parser.add_argument("--force", action="store_true", help="run again saved episodes")
    parser.add_argument("--dry-run", action="store_true", help="list the episodes to run")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument(
        "--no-summary", action="store_true", help="do not rewrite combined_summary.csv"
    )
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true", help="run on uncommitted changes")
    args = parser.parse_args()
    if args.seed in TEST_SEEDS:
        raise SystemExit("test seeds are never used to tune anything")
    if args.probe:
        probe(args.networks, args.seed)
        return
    if args.profile_congestion:
        profile_congestion(args.networks, args.demands, args.seed, args.jobs)
        return
    if not args.summary_only:
        tasks = tasks_for(args)
        if not args.force:
            tasks = [t for t in tasks if not (OUT / "raw" / f"{rid_of(t)}.csv").exists()]
        plain = [t for t in tasks if t[0] not in WITH_LLM]
        llm = [t for t in tasks if t[0] in WITH_LLM]
        print(f"{len(plain)} episodes without LLM, {len(llm)} with the local model")
        if args.dry_run:
            for t in plain + llm:
                print(" ", rid_of(t))
            return
        if git_commit().endswith("-dirty") and not args.allow_dirty:
            # every row stores the commit: commit first (the summary of a previous run too)
            raise SystemExit("tracked files have uncommitted changes: commit them first")
        (OUT / "raw").mkdir(parents=True, exist_ok=True)
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for row in pool.map(run_task, plain):
                print(f"done {row['run_id']} ({row['sim_wall_time_s']:.0f} s)", flush=True)
        if llm:
            settings = load_settings()
            Ollama(settings.model, settings.options).warm_up()
        for t in llm:  # alone: the measured latency must not include other simulations
            row = run_task(t)
            print(f"done {row['run_id']} ({row['sim_wall_time_s']:.0f} s)", flush=True)
    if args.no_summary:  # batches: a rewritten summary would mark the next batch -dirty
        return
    table = summarise()
    if not table.empty:
        table.to_csv(OUT / "combined_summary.csv", index=False)
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
