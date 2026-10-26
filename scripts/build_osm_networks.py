#!/usr/bin/env python3
"""
build_osm_networks.py
=====================
Downloads OSM data from Overpass API and compiles SUMO road networks via
netconvert for the Monaco and Tunis (real-world) scenarios.

Usage
-----
    # Build both (skip if already built)
    python scripts/build_osm_networks.py

    # Build only one
    python scripts/build_osm_networks.py --nets monaco
    python scripts/build_osm_networks.py --nets tunis

    # Force rebuild even if .net.xml already exists
    python scripts/build_osm_networks.py --force

    # Use the old network name (backward-compatible)
    python scripts/build_osm_networks.py --nets real_district

What it does
------------
For each network name the script calls:

    python -m cotraffic networks <name> [--force]

which in turn:
  1. Loads  configs/networks/<name>.yaml
  2. Downloads the highway OSM extract for the bbox via Overpass API (cached)
  3. Runs netconvert with the parameters in the YAML to produce
     sumo_files/<name>/<name>.net.xml

Prerequisites
-------------
- SUMO ≥ 1.20 installed and SUMO_HOME set (or netconvert on PATH)
- Python ≥ 3.10 with cotraffic installed  (`pip install -e .` from repo root)
- Internet access (first run only — OSM extract is cached afterwards)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Networks supported by this helper. real_district is kept for backward compat.
OSM_NETWORKS = ["monaco", "tunis", "real_district", "real_district_ped"]


def build(name: str, force: bool) -> bool:
    """Run `python -m cotraffic networks <name>` and return True on success."""
    cmd = [sys.executable, "-m", "cotraffic", "networks", name]
    if force:
        cmd.append("--force")
    print(f"\n{'='*60}")
    print(f"  Building network: {name}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"\n[ERROR] Failed to build network '{name}' (exit {result.returncode})", file=sys.stderr)
        return False
    out = REPO_ROOT / "sumo_files" / name / f"{name}.net.xml"
    if out.is_file():
        size_kb = out.stat().st_size // 1024
        print(f"\n[OK] {out.relative_to(REPO_ROOT)}  ({size_kb} KB)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--nets",
        nargs="+",
        default=["monaco", "tunis"],
        choices=OSM_NETWORKS,
        metavar="NET",
        help=f"Network name(s) to build. Choices: {OSM_NETWORKS}. Default: monaco tunis",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if the .net.xml already exists",
    )
    args = parser.parse_args()

    failures = []
    for name in args.nets:
        ok = build(name, args.force)
        if not ok:
            failures.append(name)

    print()
    if failures:
        print(f"[FAILED] {len(failures)} network(s) failed to build: {failures}", file=sys.stderr)
        sys.exit(1)
    else:
        built = args.nets
        print(f"[DONE] Successfully built {len(built)} network(s): {built}")
        print()
        print("Next steps:")
        for name in built:
            net = REPO_ROOT / "sumo_files" / name / f"{name}.net.xml"
            print(f"  sumo-gui {net}")
        print()
        print("Run a quick smoke test with:")
        for name in built:
            print(f"  python -m cotraffic episode --net {name} --seconds 120")


if __name__ == "__main__":
    main()
