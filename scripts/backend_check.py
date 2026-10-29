"""Do libsumo and TraCI give the same episodes? Saved TraCI rows played again on libsumo.

    python scripts/backend_check.py [--jobs 4]   # -> results/exploration/combined/backend_check.csv

The rows of the combined study written before the column ``sumo_backend`` ran on TraCI;
the later ones run on libsumo (no sockets: over TraCI, the ports drawn by workers starting
together can collide). The episodes below cover both networks, every scenario and every
kind of controller of the study; each is played again on libsumo in a temporary folder
(the saved row is not touched) and every measure of the row is compared, except the
computing times.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

os.environ["LIBSUMO_AS_TRACI"] = "1"  # before any binding is imported, inherited by workers
sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_eval as ce  # noqa: E402

from cotraffic.utils.sumo import use_libsumo  # noqa: E402

SAVED = ce.OUT  # the saved rows; a worker moves ce.OUT to its temporary folder

# (method, network, scenario, demand, seed, training run, parameter), all saved on TraCI
TASKS = [
    ("mp", "grid4x4", "normal", "peak", 1001, 0, None),
    ("team_rules", "real_district", "emergency", "peak", 1001, 0, None),
    ("ped_rule_mp", "grid4x4", "pedestrians", "medium", 1002, 0, None),
    ("coop_full", "grid4x4", "incident", "medium", 1002, 2, None),
    ("coop_full_evrule_switch", "real_district", "emergency", "medium", 1002, 2, None),
    ("coop_full_pedrule_switch", "grid4x4", "pedestrians", "peak", 1002, 1, None),
    ("hybrid_h1", "grid4x4", "incident", "peak", 1000, 1, 90.0),
    ("hybrid_h2", "real_district", "normal", "peak", 1001, 3, 2.0),
]
TIMES = ("wall", "inference_ms", "latency")  # computing times: not part of the episode


def check(task: tuple) -> dict:
    saved = pd.read_csv(SAVED / "raw" / f"{ce.rid_of(task)}.csv").iloc[0]
    ce.OUT = Path(tempfile.mkdtemp())  # this worker's rows, calls and logs go there
    ce.run_task(task)
    # read back from its file, as the saved row: the same rounding of the decimals
    row = pd.read_csv(ce.OUT / "raw" / f"{ce.rid_of(task)}.csv").iloc[0]
    compared, different = 0, []
    for k, v in saved.items():
        if k not in row or any(t in k for t in TIMES) or k in ("git_commit", "run_id"):
            continue
        new = row[k]
        same = (pd.isna(v) and pd.isna(new)) or v == new or str(v) == str(new)
        compared += 1
        if not same:
            different.append(f"{k}: {v} / {new}")
    return {
        "run_id": saved["run_id"],
        "saved_commit": saved["git_commit"],
        "backend": "libsumo" if use_libsumo() else "traci",
        "measures_compared": compared,
        "measures_different": len(different),
        "differences": "; ".join(different[:5]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(check, TASKS))
    table = pd.DataFrame(rows)
    table.to_csv(SAVED / "backend_check.csv", index=False)
    print(table[["run_id", "backend", "measures_compared", "measures_different"]].to_string())
    print("identical" if (table.measures_different == 0).all() else "DIFFERENT")


if __name__ == "__main__":
    main()
