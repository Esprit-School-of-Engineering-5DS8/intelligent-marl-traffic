"""Step 2 pipeline: the remaining validation tasks, one after the other, unattended.

    python scripts/llm_step2.py        # resumes where it stopped; safe to start again

A task is skipped when its output exists, waited for when another process is running it
(its log changed in the last 10 minutes), and run otherwise. LLM calls never run at the
same time as other computations, so that the measured latencies stay honest.

The choices between tasks follow rules fixed before the results are seen, on validation
seed 1000 only, and are written to results/exploration/llm_benchmark/step2_choice.json:

* model and beta: among the (model, beta) pairs of the zero-shot benchmark with at least
  95 % valid JSON and a p95 latency of at most 20 s, the highest mean gain on waiting;
  within 0.05 points of it, the lowest p50 latency;
* technique (zero, brief, few): the same rule on the chosen model and beta;
* self-consistency (vote over 3 answers): kept only if it raises the mean gain on
  waiting and its p95 latency stays at most 45 s;
* period N: the highest mean gain on waiting over the scenarios; within 0.5 points of
  it, the longest period (fewer calls).

Gains are against COOP-FULL alone: positive = better (less waiting).

These rules pick the best value even when differences are within noise: the report says
so, and step 4 tests the chosen setting on the test seeds against the placebo.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from cotraffic.paths import REPO_ROOT, RESULTS_DIR

LOGS = RESULTS_DIR / "tmp" / "llm" / "logs"
BENCH = RESULTS_DIR / "exploration" / "llm_benchmark"
CHOICE = BENCH / "step2_choice.json"
FRESH_S = 600
MODELS = ["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3:1.7b", "llama3.2:3b", "qwen2.5:3b", "phi4-mini"]


def say(text: str) -> None:
    print(f"{datetime.now():%d/%m %H:%M:%S}  {text}", flush=True)


def task(name: str, script: str, args: list[str], output: Path) -> None:
    log = LOGS / f"{name}.log"
    while not output.exists() and log.exists() and time.time() - log.stat().st_mtime < FRESH_S:
        say(f"{name}: running in another process, waiting")
        time.sleep(60)
    if output.exists():
        say(f"{name}: done ({output.name})")
        return
    say(f"{name}: starting {script} {' '.join(args)}")
    with log.open("w", encoding="utf-8") as f:
        code = subprocess.run(
            [sys.executable, "-u", str(REPO_ROOT / "scripts" / script), *args],
            cwd=REPO_ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
        ).returncode
    if code != 0 or not output.exists():
        say(f"{name}: FAILED (exit code {code}), see {log}")
        raise SystemExit(1)
    say(f"{name}: done")


def best(rows: pd.DataFrame, tie: float, by: str) -> pd.Series:  # [Exigence 2] règle de choix
    """Highest mean gain on waiting; within ``tie`` points of it, the lowest ``by``."""
    top = rows["gain_waiting_%"].max()
    near = rows[rows["gain_waiting_%"] >= top - tie]
    return near.sort_values(by).iloc[0]


def save(choice: dict) -> None:
    CHOICE.write_text(json.dumps(choice, indent=2, ensure_ascii=False), encoding="utf-8")
    say(f"choice: {choice}")


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    task(
        "fewshot",
        "llm_fewshot.py",
        ["--set", "few", "--beta", "4", "--jobs", "6"],
        RESULTS_DIR / "exploration" / "llm_fewshot" / "few_beta4_kinds.csv",
    )
    task(
        "v2_zero",
        "llm_benchmark.py",
        ["--models", *MODELS, "--techniques", "zero", "--num-predict", "96"]
        + ["--betas", "2", "4", "--jobs", "6", "--tag", "v2_zero"],
        BENCH / "v2_zero_summary.csv",
    )

    zero = pd.read_csv(BENCH / "v2_zero_summary.csv")  # [Exigence 2] choix du modèle
    llm = zero[(zero.technique == "zero") & zero["gain_waiting_%"].notna()]
    ok = llm[(llm["json_valid_%"] >= 95) & (llm["latency_p95_s"] <= 20)]
    pick = best(ok if len(ok) else llm, 0.05, "latency_p50_s")
    choice = {
        "model": pick.model,
        "beta": float(pick.beta),
        "zero_gain_waiting_%": float(pick["gain_waiting_%"]),
        "rule": "model and beta: valid >= 95 %, p95 <= 20 s, highest gain on waiting",
        "convention": "gain > 0 = better than COOP-FULL alone",
    }
    save(choice)
    model, beta = choice["model"], f"{choice['beta']:g}"

    task(
        "v2_tech",
        "llm_benchmark.py",
        ["--models", model, "--techniques", "zero", "brief", "few", "--num-ctx", "4096"]
        + ["--num-predict", "96", "--betas", beta, "--jobs", "6", "--tag", "v2_tech"],
        BENCH / "v2_tech_summary.csv",
    )
    tech = pd.read_csv(BENCH / "v2_tech_summary.csv")  # [Exigence 4] choix de la technique
    tech = tech[(tech.model == model) & tech["gain_waiting_%"].notna()]
    pick = best(tech, 0.05, "latency_p50_s")
    choice.update(
        {"technique": pick.technique, "technique_gain_waiting_%": float(pick["gain_waiting_%"])}
    )
    save(choice)
    technique = choice["technique"]

    task(
        "v2_vote",
        "llm_benchmark.py",
        ["--models", model, "--techniques", technique, "--vote", "3", "--num-ctx", "4096"]
        + ["--num-predict", "96", "--betas", beta, "--jobs", "6", "--tag", "v2_vote"],
        BENCH / "v2_vote_summary.csv",
    )
    vote = pd.read_csv(BENCH / "v2_vote_summary.csv")  # [Exigence 4] vote retenu ou non
    vote = vote[(vote.model == model) & vote["gain_waiting_%"].notna()].iloc[0]
    keep = (
        vote["gain_waiting_%"] > choice["technique_gain_waiting_%"] and vote["latency_p95_s"] <= 45
    )
    choice.update(
        {
            "vote": 3 if keep else 1,
            "vote_gain_waiting_%": float(vote["gain_waiting_%"]),
            "vote_latency_p95_s": float(vote["latency_p95_s"]),
        }
    )
    save(choice)

    task(
        "period",
        "llm_period.py",
        ["--model", model, "--technique", technique, "--beta", beta]
        + ["--vote", str(choice["vote"]), "--num-ctx", "4096"],
        RESULTS_DIR / "exploration" / "llm_period" / "period_summary.csv",
    )
    period = pd.read_csv(RESULTS_DIR / "exploration" / "llm_period" / "period_summary.csv")
    per_n = (
        period.groupby("period_s")["gain_mean_waiting_time_%"]
        .mean()
        .rename("gain_waiting_%")
        .reset_index()
    )
    per_n["minus_period"] = -per_n.period_s  # [Exigence 3] choix de la période N
    pick = best(per_n, 0.5, "minus_period")
    choice.update(
        {
            "period_s": float(pick.period_s),
            "period_gain_waiting_%": round(float(pick["gain_waiting_%"]), 2),
            "done": f"{datetime.now():%Y-%m-%d %H:%M}",
        }
    )
    save(choice)
    say("step 2 tasks finished: write-up and commit remain")


if __name__ == "__main__":
    main()
