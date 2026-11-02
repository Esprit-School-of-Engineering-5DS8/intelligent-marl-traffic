"""Exploratory study "LLM in the decision loop": the candidate with the LLM strategist.

    python scripts/llm_loop.py run --seeds 1000            # validation seed, 14 main cells
    python scripts/llm_loop.py run --seeds 0 1 2 3 4 --cells all
    python scripts/llm_loop.py report                      # -> results/llm_loop/report.md

The final candidate (H2 beta 4: COOP-FULL pushed towards Max-Pressure, EV-RULE, the shield)
gets a fourth layer on top: every 5 minutes the local language model (configs/llm.yaml)
chooses the mode of the whole network (src/cotraffic/llm/strategist.py). Written and run
AFTER the preregistered final evaluation, which it does not replace: every result here is
exploratory. The validation seed comes first (the oracle and its placebo were measured on
it, with the same three modes and the same window); test seeds follow, with the model of
training run 1, against the candidate's own episodes of the final evaluation (same model,
same seeds). Rows go to results/llm_loop/raw/, each call of the model to
results/llm_loop/calls/ (state read, mode chosen, reason, latency).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # identical episodes, 3-4 times faster

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_analysis as ca  # noqa: E402
import combined_eval as ce  # noqa: E402
import combined_figures as cf  # noqa: E402
from hybrid_rank import md  # noqa: E402

from cotraffic.controllers.registry import make_controller  # noqa: E402
from cotraffic.evaluation.runner import run_episode, run_id  # noqa: E402
from cotraffic.llm.client import Ollama  # noqa: E402
from cotraffic.llm.settings import load_settings  # noqa: E402
from cotraffic.llm.strategist import (  # noqa: E402
    LlmStrategist,
    LlmStrategyPolicy,
    StrategistPrompt,
)
from cotraffic.paths import RESULTS_DIR  # noqa: E402
from cotraffic.utils.io import write_row  # noqa: E402

OUT = RESULTS_DIR / "llm_loop"
METHOD = "hybrid_h2_llmstrat"
BETA = 4.0
WINDOW_S = 300.0
PROMPT = "strategist-v1"
MAIN = [tuple(c.split()) for c in cf.ORDER[:14]]
ALL = [tuple(c.split()) for c in cf.ORDER]


def task_id(task: tuple) -> str:
    network, scenario, demand, seed, run = task
    scenarios = [s for s in [scenario] if s != "normal"]
    return run_id(METHOD, network, scenarios, demand, seed, f"t{run}-b{BETA:g}")


def run_task(task: tuple) -> dict:
    network, scenario, demand, seed, run = task
    settings = load_settings()
    client = Ollama(settings.model, settings.options)
    prompt = StrategistPrompt.load(PROMPT)
    ckpt = ce.checkpoint(network, run)
    strategist = LlmStrategist(client, prompt, WINDOW_S)
    policy = LlmStrategyPolicy(make_controller("coop_full", ckpt), strategist, BETA, METHOD)
    mode = "validation" if seed >= 1000 else "evaluation"
    row = run_episode(METHOD, network, demand, [scenario], seed, checkpoint=ckpt,
                      tag=f"t{run}-b{BETA:g}", raw_dir=OUT / "raw", logs_dir=OUT / "logs",
                      controller=policy, mode=mode)  # fmt: skip
    info = client.fingerprint()
    row.update({
        "mechanism": "ppo + logit_bias(max_pressure) + switch(EV-RULE) + llm_strategy(mode/5 min)",
        "train_run": run, "llm_model": settings.model, "llm_digest": info.get("digest", ""),
        "prompt": prompt.version, "window_s": WINDOW_S, "beta": BETA, "protocol_mode": mode,
        "sumo_backend": "libsumo", **policy.summary(),
    })  # fmt: skip
    rid = task_id(task)
    write_row(OUT / "raw" / f"{rid}.csv", row)
    calls = OUT / "calls"
    calls.mkdir(parents=True, exist_ok=True)
    with (calls / f"{rid}.jsonl").open("w", encoding="utf-8") as f:
        for c in policy.call_log():
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return row


def cmd_run(args) -> None:
    cells = ALL if args.cells == "all" else MAIN
    # seed by seed: partial results already cover every cell
    tasks = [(n, s, d, seed, run) for seed in args.seeds for run in args.runs
             for n, s, d in cells]  # fmt: skip
    todo = [t for t in tasks if not (OUT / "raw" / f"{task_id(t)}.csv").is_file()]
    print(f"{len(todo)} episodes to run ({len(tasks) - len(todo)} already there)", flush=True)
    start = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for k, row in enumerate(pool.map(run_task, todo), 1):
            print(f"[{k}/{len(todo)}] {row['run_id']}: trajet {row['mean_travel_time']:.1f} s, "
                  f"attente {row['mean_waiting_time']:.1f} s, modes {row['llm_schedule']} "
                  f"({(time.time() - start) / 60:.0f} min)", flush=True)  # fmt: skip


# ---------------------------------------------------------------- report
def candidate_rows(seed_kind: str) -> pd.DataFrame:
    """The candidate's own episodes (model t1): validation seed 1000 or test seeds 0-4."""
    folder = "exploration/combined/raw" if seed_kind == "validation" else "combined/raw"
    raw = RESULTS_DIR / folder
    df = ca.load(raw)
    return df[(df.method == "hybrid_h2") & (df.param == BETA) & (df.run == 1)]


def report_rows(llm: pd.DataFrame, cand: pd.DataFrame) -> list[dict]:
    rows = []
    for (net, scen, dem), cell in llm.groupby(["network", "scenario", "demand"]):
        base = cand[(cand.network == net) & (cand.scenario == scen) & (cand.demand == dem)]
        seeds = sorted(set(cell.seed) & set(base.seed))
        if not seeds:
            continue
        a, b = cell.set_index("seed").loc[seeds], base.set_index("seed").loc[seeds]
        line = {"network": net, "scenario": scen, "demand": dem, "seeds": len(seeds)}
        for metric, name in (("mean_travel_time", "travel"), ("mean_waiting_time", "waiting"),
                             ("ev_delay", "ambulances")):  # fmt: skip
            if metric not in a or a[metric].isna().all():
                continue
            x, y = a[metric].astype(float).to_numpy(), b[metric].astype(float).to_numpy()
            line[f"{name}_llm"] = round(float(x.mean()), 2)
            line[f"{name}_candidate"] = round(float(y.mean()), 2)
            line[f"{name}_gain_pct"] = round(100 * float(y.mean() - x.mean()) / float(y.mean()), 2)
        for m in ("equilibre", "fluidite", "agent"):
            line[f"share_{m}"] = round(float(cell[f"llm_share_{m}"].mean()), 3)
        line["switches"] = round(float(cell["llm_mode_switches"].mean()), 1)
        line["valid_rate"] = round(float(cell["llm_valid_rate"].mean()), 3)
        line["latency_p50_s"] = round(float(cell["llm_latency_p50_s"].mean()), 2)
        rows.append(line)
    return rows


def cmd_report(_args) -> None:
    files = sorted((OUT / "raw").glob("*.csv"))
    if not files:
        print("no row yet")
        return
    llm = pd.DataFrame([pd.read_csv(p).iloc[0].to_dict() for p in files])
    out = {}
    for kind, sel in (("validation", llm.seed >= 1000), ("test", llm.seed < 1000)):
        if sel.any():
            out[kind] = report_rows(llm[sel], candidate_rows(kind))
    (OUT / "report.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    lines = ["# LLM dans la boucle de décision : la candidate + le LLM stratège (exploratoire)", ""]
    for kind, rows in out.items():
        t = pd.DataFrame(rows)
        lines += [f"## Graines de {kind}", "", md(t), ""]
        for name in ("travel", "waiting", "ambulances"):
            col = f"{name}_gain_pct"
            if col in t:
                lines.append(f"- {name} : gain moyen {t[col].mean():+.2f} % "
                             f"(min {t[col].min():+.2f}, max {t[col].max():+.2f})")  # fmt: skip
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--seeds", type=int, nargs="+", default=[1000])
    p.add_argument("--runs", type=int, nargs="+", default=[1])
    p.add_argument("--cells", choices=["main", "all"], default="main")
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_run)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    args.func(args)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
