"""Follow validation runs while they execute (refreshes every few seconds; Ctrl+C to stop).

    python scripts/watch_runs.py [--every 20]

For each batch (ensemble, validate) it shows how many runs are finished out of the
expected total, the runs in progress, and the latest results with their travel time,
waiting time and unfinished vehicles (a gridlocked run has many).
"""

from __future__ import annotations

import argparse
import os
import time

import pandas as pd

from cotraffic.paths import RESULTS_DIR

TMP = RESULTS_DIR / "tmp"
BATCHES = {"ensemble": 60, "validate": 106}


def finished(batch: str) -> pd.DataFrame:
    files = sorted((TMP / batch / "raw").glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        return pd.DataFrame()
    rows = [pd.read_csv(f).iloc[0] for f in files]
    df = pd.DataFrame(rows)
    df["finished_at"] = [time.strftime("%H:%M", time.localtime(f.stat().st_mtime)) for f in files]
    return df


def running(done: set[str]) -> list[str]:
    """Run folders SUMO is writing to right now (no result row yet)."""
    names = []
    for path in TMP.iterdir():
        recent = time.time() - path.stat().st_mtime < 600
        if path.is_dir() and "__" in path.name and path.name not in done and recent:
            names.append(path.name)
    return sorted(names)


def show() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print(time.strftime("%H:%M:%S"), "- validation runs (graines de validation)\n")
    done_ids: set[str] = set()
    for batch, total in BATCHES.items():
        df = finished(batch)
        n = len(df)
        bar = "#" * int(30 * n / total) + "." * (30 - int(30 * n / total))
        print(f"{batch:9s} [{bar}] {n}/{total}")
        if n:
            done_ids |= set(df["run_id"])
            cols = ["finished_at", "run_id", "mean_travel_time", "mean_waiting_time", "unfinished"]
            last = df[[c for c in cols if c in df]].tail(6)
            print(last.round(1).to_string(index=False))
        print()
    now = running(done_ids)
    print("en cours :", ", ".join(now) if now else "aucun")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, default=20, help="seconds between refreshes")
    args = parser.parse_args()
    try:
        while True:
            show()
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
