"""Call period N of the advisor: full validation episodes with the LLM in the loop.

    python scripts/llm_period.py --model qwen2.5:1.5b --technique zero --beta 4 \
        [--vote 1] [--periods 180 300 600] [--seed 1000] [--scenarios incident ...] [--tag t]

Per scenario (grid4x4, peak), one COOP-FULL episode without advice, then one episode per
period N with the advisor (events trigger a call at once; otherwise a call every N
seconds). The LLM episodes run one after the other, never in parallel: the latency of each
call is measured and sets the delay before its advice applies. Validation seeds only.

Rows go to results/exploration/llm_period/raw/ (never results/raw), the audit log of every
call to results/exploration/llm_period/calls/, the comparison to period_summary.csv.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import pandas as pd

from cotraffic.controllers.registry import make_controller
from cotraffic.evaluation.runner import run_episode
from cotraffic.llm.advised import AdvisedPolicy, AdvisorConfig
from cotraffic.llm.client import Ollama, Options
from cotraffic.llm.progress import Progress
from cotraffic.llm.prompts import DEFAULT_VERSION, load
from cotraffic.llm.sources import llm_source
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TEST_SEEDS
from cotraffic.utils.io import write_row

OUT = RESULTS_DIR / "exploration" / "llm_period"
SCENARIOS = ["incident", "emergency", "sensor_noise", "comm_dropout_30", "pedestrians", "normal"]
NETWORK, DEMAND = "grid4x4", "peak"
METRICS = [
    "mean_waiting_time",
    "mean_travel_time",
    "p95_waiting_time",
    "ev_delay",
    "ped_mean_waiting_time",
    "throughput_per_h",
]


def checkpoint():
    return CHECKPOINTS_DIR / "coop_full" / NETWORK / "seed1.zip"


def baseline(task) -> dict:
    scenario, seed = task
    return run_episode(
        "coop_full",
        NETWORK,
        DEMAND,
        [scenario],
        seed,
        checkpoint=checkpoint(),
        tag="noadvice",
        raw_dir=OUT / "raw",
        logs_dir=OUT / "logs",
        mode="validation",
    )


def advised(scenario: str, seed: int, period: float, args, options: Options) -> dict:
    client = Ollama(args.model, options)
    prompt = load(args.prompt, args.technique)
    cfg = AdvisorConfig(beta=args.beta, period_s=period, latency=args.latency)
    source, label = llm_source(
        args.model, args.technique, options, args.prompt, args.vote, args.vote_temperature
    )
    policy = AdvisedPolicy(make_controller("coop_full", checkpoint()), source, cfg)
    tag = f"N{period:g}" + (f"-{args.tag}" if args.tag else "")
    row = run_episode(
        "coop_full_llm",
        NETWORK,
        DEMAND,
        [scenario],
        seed,
        checkpoint=checkpoint(),
        tag=tag,
        raw_dir=OUT / "raw",
        logs_dir=OUT / "logs",
        controller=policy,
        mode="validation",
    )
    info = client.fingerprint()
    row.update(
        {
            "llm_model": args.model,
            "llm_digest": info.get("digest", ""),
            "llm_quantization": info.get("quantization", ""),
            "prompt": prompt.id,
            "technique": label,
            "vote_k": args.vote,
            "mechanism": "bias",
            "beta": args.beta,
            "period_s": period,
            "latency_mode": args.latency,
            **{f"opt_{k}": v for k, v in asdict(options).items()},
            **policy.summary(),
        }
    )
    write_row(OUT / "raw" / f"{row['run_id']}.csv", row)
    calls = OUT / "calls"
    calls.mkdir(parents=True, exist_ok=True)
    with (calls / f"{row['run_id']}.jsonl").open("w", encoding="utf-8") as f:
        for c in policy.calls:
            f.write(json.dumps(asdict(c), default=str) + "\n")
    return row


def summarise(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    base = df[df.method == "coop_full"].set_index("scenario")
    out = []
    for r in df[df.method == "coop_full_llm"].itertuples():
        b = base.loc[r.scenario]
        row = {"scenario": r.scenario, "period_s": r.period_s}
        for m in METRICS:
            if m in df and pd.notna(getattr(r, m)) and pd.notna(b[m]):
                row[f"{m}_change_%"] = round(100 * (getattr(r, m) - b[m]) / max(abs(b[m]), 1e-9), 2)
        row.update(
            {
                "llm_calls": r.llm_calls,
                "llm_valid_rate": round(r.llm_valid_rate, 2),
                "llm_latency_p50_s": round(r.llm_latency_p50_s, 1),
                "llm_changed_decisions": r.llm_changed_decisions,
                "wall_time_s": round(r.sim_wall_time_s, 0),
                "wall_time_noadvice_s": round(b.sim_wall_time_s, 0),
            }
        )
        out.append(row)
    return pd.DataFrame(out).sort_values(["scenario", "period_s"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--technique", default="zero")
    parser.add_argument("--prompt", default=DEFAULT_VERSION)
    parser.add_argument("--beta", type=float, required=True)
    parser.add_argument("--periods", nargs="+", type=float, default=[180.0, 300.0, 600.0])
    parser.add_argument("--vote", type=int, default=1, help="self-consistency: k samples")
    parser.add_argument("--vote-temperature", type=float, default=0.7)
    parser.add_argument("--latency", default="measured")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--scenarios", nargs="+", default=SCENARIOS)
    parser.add_argument("--num-predict", type=int, default=96)
    parser.add_argument("--num-ctx", type=int, default=2048)
    parser.add_argument("--jobs", type=int, default=3, help="workers for the no-advice runs")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    if args.seed in TEST_SEEDS:
        raise SystemExit("test seeds are never used to tune anything")

    options = Options(num_predict=args.num_predict, num_ctx=args.num_ctx)
    progress = Progress("episodes", len(args.scenarios) * (1 + len(args.periods)))
    rows = []
    # without the LLM, episodes can run in parallel; never at the same time as LLM calls
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(baseline, [(s, args.seed) for s in args.scenarios]):
            rows.append(row)
            progress.tick()
    Ollama(args.model, options).warm_up()
    for scenario in args.scenarios:
        for period in args.periods:
            row = advised(scenario, args.seed, period, args, options)
            rows.append(row)
            progress.tick()
            print(
                f"{scenario:16s} N={period:4.0f}s calls {row['llm_calls']:3d} "
                f"waiting {row['mean_waiting_time']:.1f}s wall {row['sim_wall_time_s']:.0f}s",
                flush=True,
            )
    table = summarise(rows)
    table.to_csv(OUT / f"period_summary{('_' + args.tag) if args.tag else ''}.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
