"""Static NS/EW axis audit for the LLM team port.

The team's directive layer speaks in `NS`/`EW` groups plus an optional `phase_index`.
Integration uses one action per green phase, so the port derives an axis for every green
phase from the network geometry. This script reads a built net and reports, per signalised
junction, the axis of each green phase and any case the mapping cannot resolve cleanly.

    python scripts/audit_llm_team_axes.py --nets sf_mission_2x2 sf_mission_3x3 tunis monaco
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cotraffic.networks.topology import lane_approach_side, load_net

NET_DIR = ROOT / "sumo_files"


def _vehicle_lane(net, lane_id: str) -> bool:
    try:
        lane = net.getLane(lane_id)
    except (KeyError, AttributeError):
        return False
    try:
        return bool(lane.allows("passenger"))
    except Exception:  # noqa: BLE001 - permissions are optional in old nets
        return True


def audit_network(network: str) -> list[dict]:
    net_file = NET_DIR / network / f"{network}.net.xml"
    if not net_file.is_file():
        print(f"{network}: net not built ({net_file})")
        return []
    net = load_net(str(net_file))
    root = ET.parse(net_file).getroot()

    # link index -> approach lane, per TLS (vehicle connections only)
    links: dict[str, dict[int, str]] = {}
    for conn in root.findall("connection"):
        tls_id = conn.get("tl")
        index = conn.get("linkIndex")
        if not tls_id or index is None:
            continue
        lane_id = f"{conn.get('from')}_{conn.get('fromLane', '0')}"
        if not _vehicle_lane(net, lane_id):
            continue
        links.setdefault(tls_id, {})[int(index)] = lane_id

    rows = []
    for logic in root.findall("tlLogic"):
        tls_id = logic.get("id")
        if tls_id not in links:
            continue
        phases = []
        for index, phase in enumerate(logic.findall("phase")):
            state = phase.get("state") or ""
            ns = ew = 0
            serving = 0
            for link_index, char in enumerate(state):
                if char not in ("g", "G"):
                    continue
                lane_id = links[tls_id].get(link_index)
                if lane_id is None:
                    continue
                serving += 1
                side = lane_approach_side(net, lane_id)
                if side in ("north", "south"):
                    ns += 1
                else:
                    ew += 1
            if not serving:
                continue  # all-red or yellow-only phase
            phases.append(
                {
                    "phase": index,
                    "axis": "NS" if ns >= ew else "EW",
                    "ns_links": ns,
                    "ew_links": ew,
                    "mixed": ns > 0 and ew > 0,
                }
            )
        axes = [p["axis"] for p in phases]
        rows.append(
            {
                "tls": tls_id,
                "green_phases": len(phases),
                "ns": axes.count("NS"),
                "ew": axes.count("EW"),
                "mixed": sum(1 for p in phases if p["mixed"]),
                "phases": phases,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nets",
        nargs="+",
        default=["sf_mission_2x2", "sf_mission_3x3", "tunis", "monaco"],
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    problems = 0
    for network in args.nets:
        rows = audit_network(network)
        if not rows:
            continue
        single_axis = [r for r in rows if r["ns"] == 0 or r["ew"] == 0]
        mixed = [r for r in rows if r["mixed"]]
        both = [r for r in rows if r["ns"] and r["ew"]]
        print(
            f"\n{network}: {len(rows)} junctions | "
            f"{len(both)} with both axes | "
            f"{len(single_axis)} single-axis | "
            f"{len(mixed)} with a mixed green phase"
        )
        for row in rows:
            flag = ""
            if row["ns"] == 0 or row["ew"] == 0:
                flag += " SINGLE-AXIS"
            if row["mixed"]:
                flag += " MIXED"
            print(
                f"  {row['tls']}: {row['green_phases']} green phases "
                f"(NS {row['ns']}, EW {row['ew']}){flag}"
            )
            if args.verbose or flag:
                for phase in row["phases"]:
                    print(
                        f"      phase {phase['phase']}: {phase['axis']} "
                        f"(ns {phase['ns_links']}, ew {phase['ew_links']})"
                    )
        problems += len(single_axis) + len(mixed)
    print(f"\n{'OK' if problems == 0 else str(problems) + ' issue(s)'}")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
