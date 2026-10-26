"""Progress of the LLM-in-the-loop work, step by step (read-only: reads logs and outputs).

    python scripts/llm_watch.py            # one status table
    python scripts/llm_watch.py --follow   # refreshed every 30 s (Ctrl+C to stop)

A task is done when its output file exists, running when its log changed in the last 10
minutes, interrupted when its log stopped changing before the output was written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cotraffic.paths import RESULTS_DIR

LOGS = RESULTS_DIR / "tmp" / "llm" / "logs"
BENCH = RESULTS_DIR / "exploration" / "llm_benchmark"
PHASES = {"calls": "appels au LLM", "replays": "rejeux SUMO"}
LINE = re.compile(r"PROGRESS (\w+) (\d+)/(\d+) elapsed=(\d+) eta=(-?\d+)")


@dataclass
class Task:
    label: str
    log: str  # file name in results/tmp/llm/logs
    output: Path  # exists when the task is done


STEP2 = [
    Task(
        "Exemples few-shot (graine d'entraînement 100001, choix par gain moyen)",
        "fewshot.log",
        RESULTS_DIR / "exploration" / "llm_fewshot" / "few_beta4_kinds.csv",
    ),
    Task(
        "Benchmark v2 zero-shot (6 modèles, beta 2 et 4)",
        "v2_zero.log",
        BENCH / "v2_zero_summary.csv",
    ),
    Task("Techniques zero / brief / few", "v2_tech.log", BENCH / "v2_tech_summary.csv"),
    Task(
        "Hyperparamètres : self-consistency (vote à 3), budgets de tokens",
        "v2_vote.log",
        BENCH / "v2_vote_summary.csv",
    ),
    Task(
        "Période N (3, 5, 10 min), épisodes complets",
        "period.log",
        RESULTS_DIR / "exploration" / "llm_period" / "period_summary.csv",
    ),
]


VALIDATION = [
    Task(
        "Oracle (validation) et jeu de données LoRA (graines d'entraînement)",
        "dataset.log",
        RESULTS_DIR / "exploration" / "llm_lora" / "llm_lora_val.jsonl",
    ),
    Task(
        "Rejeu SUMO des prédictions LoRA et prompt tuning (Kaggle, prelim2)",
        "prelim_kaggle_val.log",
        BENCH / "prelim_kaggle_val_summary.csv",
    ),
]


def minutes(seconds: float) -> str:
    if seconds < 0:
        return "?"
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds // 3600:.0f} h {seconds % 3600 / 60:02.0f}"


def status(task: Task) -> tuple[str, str]:
    log = LOGS / task.log
    if task.output.exists():
        when = datetime.fromtimestamp(task.output.stat().st_mtime)
        return "fait", f"terminé le {when:%d/%m à %H:%M}"
    if not log.exists():
        return "à venir", ""
    age = time.time() - log.stat().st_mtime
    progress = [m for m in LINE.finditer(log.read_text(encoding="utf-8", errors="replace"))]
    detail = ""
    if progress:
        phase, done, total, elapsed, eta = progress[-1].groups()
        done, total, eta = int(done), int(total), int(eta)
        end = datetime.now() + timedelta(seconds=max(eta, 0) - age)
        detail = f"{PHASES.get(phase, phase)} {done}/{total} ({100 * done / total:.0f} %)"
        if eta >= 0:
            detail += f", reste ~{minutes(max(eta - age, 0))} (vers {end:%H:%M})"
    if age > 600:
        return "interrompu ?", f"{detail} - journal inchangé depuis {minutes(age)}".strip(" -")
    return "en cours", (detail or "démarrage") + f" - màj il y a {minutes(age)}"


def show() -> None:
    print(f"LLM dans la boucle - étape 2 (graine de validation 1000)   {datetime.now():%H:%M:%S}")
    print()
    for i, task in enumerate(STEP2, 1):
        state, detail = status(task)
        print(f"  [{state:^12s}] {i}. {task.label}")
        if detail:
            print(f"                 {detail}")
    print()
    print("  Validation (partie B)")
    for task in VALIDATION:
        state, detail = status(task)
        print(f"  [{state:^12s}] {task.label}")
        if detail:
            print(f"                 {detail}")
    choice = BENCH / "step2_choice.json"
    if choice.exists():
        c = json.loads(choice.read_text(encoding="utf-8"))
        names = {
            "model": "modèle",
            "beta": "beta",
            "technique": "technique",
            "vote": "vote",
            "period_s": "période (s)",
        }
        picked = ", ".join(f"{label} {c[k]}" for k, label in names.items() if k in c)
        print()
        print(f"  Choix (graine 1000) : {picked}")
    pipeline = LOGS / "step2_pipeline.log"
    if pipeline.exists():
        lines = pipeline.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if lines:
            print(f"  Enchaînement auto   : {lines[-1]}")
    print()
    print(f"  Journaux : {LOGS}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--every", type=int, default=30)
    args = parser.parse_args()
    if not args.follow:
        show()
        return
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            show()
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
