"""Merge result files produced on several machines into results/raw.

Each run writes one CSV named after its run id, so merging is a copy. A run present on
both sides with different values is reported, never silently overwritten.

    python scripts/merge_results.py path/to/other/results/raw [more folders...] [--overwrite]
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

from cotraffic.paths import RAW_DIR


def merge(sources: list[Path], overwrite: bool = False) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    copied = identical = conflicts = 0
    for source in sources:
        for path in sorted(Path(source).glob("*.csv")):
            target = RAW_DIR / path.name
            if not target.exists():
                shutil.copy2(path, target)
                copied += 1
            elif filecmp.cmp(path, target, shallow=False):
                identical += 1
            elif overwrite:
                shutil.copy2(path, target)
                copied += 1
            else:
                conflicts += 1
                print(f"conflict: {path.name} differs from the local file (kept the local one)")
    print(f"copied {copied}, identical {identical}, conflicts {conflicts}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    sys.exit(merge(args.sources, args.overwrite))
