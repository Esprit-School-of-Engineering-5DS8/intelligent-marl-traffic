"""Final evaluation of the combined study on the test seeds: run once, as preregistered.

    python scripts/combined_final.py --prereg <commit> [--dry-run] [--jobs 4]

The design (controllers, cells, seeds) is the one of docs/COMBINED_PREREGISTRATION.md,
sections 4 to 6, written out below; nothing here is chosen on the test seeds. Guards:

* ``--prereg`` is the commit that froze the preregistration; the run refuses to start if the
  preregistration, the controllers or the evaluation scripts differ from that commit, or if
  tracked files have uncommitted changes;
* rows go to results/combined/raw/ (never results/raw); an episode already written is never
  played again (a crashed run resumes with the same command, the same code and seeds);
* the episodes with the LLM run last, alone, so that its latency is not shared.

Evaluation episodes (configs/protocol.yaml: 900 s warm-up, 3600 s measured, 900 s
cool-down), libsumo, COOP-FULL training runs 1, 2 and 3.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_eval as ce  # noqa: E402

from cotraffic.paths import REPO_ROOT, RESULTS_DIR  # noqa: E402
from cotraffic.seeds import TEST_SEEDS  # noqa: E402
from cotraffic.utils.io import git_commit  # noqa: E402

OUT = RESULTS_DIR / "combined"
SEEDS = list(range(5))  # test seeds 0 to 4
RUNS = [1, 2, 3]
FROZEN = [  # must not differ from the preregistration commit
    "docs/COMBINED_PREREGISTRATION.md",
    "src/cotraffic",
    "configs",
    "scripts/combined_eval.py",
    "scripts/combined_final.py",
    "scripts/combined_analysis.py",
    "results/exploration/combined/congestion_thresholds.json",
    "results/exploration/combined/backlog_thresholds.json",
]
MAIN = [
    (n, s, d)
    for n in ("grid4x4", "real_district")
    for s in ("normal", "emergency", "incident")
    for d in ("medium", "peak")
] + [("grid4x4", "pedestrians", d) for d in ("medium", "peak")]
ROBUSTNESS = [
    ("grid4x4", "sensor_noise", "peak"),
    ("grid4x4", "comm_dropout_30", "peak"),
    ("grid4x4", "buses", "medium"),
]
GENERALISATION = [("grid8x8", "normal", "peak")]
# the candidate (H2 beta 4) and the best variant of every other family, preregistration s. 2
LEARNED = [("hybrid_h2", 4.0), ("hybrid_h1", 90.0), ("hybrid_h3", 90.0), ("coop_full", None)]
LLM_CELL = ("grid4x4", "emergency", "peak")


def controllers(network: str, scenario: str) -> list[tuple[str, float | None, list[int]]]:
    """(method, parameter, training runs) played in a cell. A controller identical by
    construction to another one in the cell is not played (preregistration, section 4)."""
    # without an emergency vehicle, V1 is COOP-FULL and EV-RULE-MP is MP; without one and
    # without pedestrians, TEAM-RULES is MP too (identical episodes in every such cell of the
    # validation seeds, the four new cells included)
    new_cell = (network, scenario) in {(n, s) for n, s, _ in ROBUSTNESS + GENERALISATION}
    # F-H3 is not played in the new cells: on the validation seed it never switched there and
    # its episodes were those of H2 beta 4 (team decision, 2026-10-29)
    out = [(m, p, RUNS) for m, p in LEARNED if not (new_cell and m == "hybrid_h3")]
    out.append(("mp", None, [0]))
    if scenario == "emergency":
        out += [("coop_full_evrule_switch", None, RUNS), ("ev_rule_mp", None, [0])]
    if scenario == "pedestrians":
        out += [("coop_full_pedrule_switch", None, RUNS), ("ped_rule_mp", None, [0])]
    if scenario in ("emergency", "pedestrians"):
        out.append(("team_rules", None, [0]))
    return out


def tasks() -> tuple[list[tuple], list[tuple]]:
    plain = [
        (m, n, s, d, seed, k, p)
        for n, s, d in MAIN + ROBUSTNESS + GENERALISATION
        for m, p, runs in controllers(n, s)
        for seed in SEEDS
        for k in runs
    ]
    n, s, d = LLM_CELL
    llm = [("hybrid_h2_llm", n, s, d, seed, 1, 4.0) for seed in SEEDS]
    return plain, llm


def run(task: tuple) -> dict:
    ce.OUT, ce.MODE = OUT, "evaluation"  # in each worker
    return ce.run_task(task)


def frozen_since(commit: str) -> list[str]:
    """Frozen paths that differ between ``commit`` and the working tree."""
    out = subprocess.run(
        ["git", "diff", "--name-only", commit, "--", *FROZEN],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prereg", required=True, help="commit that froze the preregistration")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    assert set(SEEDS) <= set(TEST_SEEDS)
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")  # inherited by the workers
    plain, llm = tasks()
    todo = [t for t in plain + llm if not (OUT / "raw" / f"{ce.rid_of(t)}.csv").exists()]
    print(f"{len(plain)} episodes without LLM, {len(llm)} with it; {len(todo)} not written yet")
    if args.dry_run:
        return
    changed = frozen_since(args.prereg)
    if changed:
        raise SystemExit(f"differs from the preregistration commit {args.prereg}: {changed}")
    if git_commit().endswith("-dirty"):
        raise SystemExit("tracked files have uncommitted changes: commit them first")
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(run, [t for t in todo if t[0] not in ce.WITH_LLM]):
            print(f"done {row['run_id']} ({row['sim_wall_time_s']:.0f} s)", flush=True)
    rest = [t for t in todo if t[0] in ce.WITH_LLM]
    if rest:
        settings = ce.load_settings()
        ce.Ollama(settings.model, settings.options).warm_up()
    for t in rest:  # alone: the measured latency must not include other simulations
        row = run(t)
        print(f"done {row['run_id']} ({row['sim_wall_time_s']:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
