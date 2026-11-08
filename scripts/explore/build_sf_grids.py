"""Build the San Francisco Mission-district 2x2 / 3x3 study networks.

The plain bbox extract still pulls in every arterial that touches the rectangle
(Van Ness, Market, side-street signals...). For the study we want exactly the
target corridors:

  sf_mission_2x2  Mission / Howard  x  6th / 7th
  sf_mission_3x3  Mission / Howard / Folsom  x  6th / 7th / 8th.

Approach (two netconvert passes):
  1. convert the downloaded extract with the arterial-only type filter, so the
     edge ids exist and carry street names;
  2. collect the ids of the arterials (streaming the intermediate net) and
     re-convert with ``--keep-edges.explicit`` restricted to them, so the final
     net contains exactly the arterial grid with signals at the target
     junctions (OSM tags + tls guess at multi-arm arterials).

Run:  python scripts/explore/build_sf_grids.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from cotraffic.networks.osm import download_osm
from cotraffic.utils.proc import run
from cotraffic.utils.sumo import binary

OUT_DIR = PROJECT / "sumo_files"

ROAD_TYPES = ("motorway", "motorway_link", "trunk", "trunk_link", "primary",
              "primary_link", "secondary", "secondary_link")

MISSION_2X2 = {
    "bbox": [-122.4134, 37.7742, -122.4090, 37.7810],
    # tight clip around the four target junctions (720 x 520 m corridor):
    "clip": [-122.4143, 37.7738, -122.4083, 37.7792],
    "names": {"Mission Street", "Howard Street", "6th Street", "7th Street"},
}
MISSION_3X3 = {
    "bbox": [-122.4180, 37.7712, -122.4090, 37.7810],
    "clip": [-122.4192, 37.7703, -122.4083, 37.7797],
    "names": {"Mission Street", "Howard Street", "Folsom Street",
              "6th Street", "7th Street", "8th Street"},
}

NETCONVERT_FLAGS = [
    "--keep-edges.by-type", ",".join(f"highway.{t}" for t in ROAD_TYPES),
    "--geometry.remove", "true",
    "--junctions.join", "true",
    "--junctions.corner-detail", "5",
    "--tls.default-type", "static",
    "--tls.yellow.time", "3",
    "--no-turnarounds.tls", "true",
    "--sidewalks.guess", "true",
    "--crossings.guess", "true",
    "--output.street-names", "true",
    "--seed", "0",
]

# First pass extras: signal nodes (tags + guess-signals) joined; every junction
# gets a usable program so the route/checksums stay stable.
PASS1_TLS = ["--tls.guess-signals", "true", "--tls.guess-signals.dist", "25",
             "--tls.join", "true", "--tls.join-dist", "30"]
# Second pass (final net): signals must come from the OSM traffic_signal tags only,
# because the kept fragments make every junction a candidate --tls.guess over the
# un-clipped corridor junctions marked by PASS1.
FINAL_TLS_FLAGS = ["--tls.guess-signals", "false", "--tls.join", "false"]


def keep_list(intermediate: Path, names: set[str]) -> list[str]:
    """Edge ids of the target arterials from the converted intermediate net.

    netconvert with --output.street-names writes the street as a ``name``
    attribute on each ``<edge>``.
    """
    ids: set[str] = set()
    for _, elem in ET.iterparse(intermediate, events=("end",)):
        if elem.tag == "edge" and elem.get("name") in names:
            ids.add(elem.get("id"))
    return sorted(ids)


def netconvert(osm_file: Path, net_file: Path, extra: list[str], clip=None) -> None:
    cmd = [
        binary("netconvert"),
        "--osm-files", str(osm_file),
        "--output-file", str(net_file),
        *NETCONVERT_FLAGS,
        *extra,
    ]
    if clip:  # cut arterial tails outside the study corridor
        cmd += ["--keep-edges.in-geo-boundary", ",".join(f"{c:.5f}" for c in clip)]
    run(cmd)


def build(case: dict, name: str) -> Path:
    out_dir = OUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    osm_file = out_dir / f"{name}.osm.xml"
    if not osm_file.is_file():
        download_osm(case["bbox"], osm_file)

    net_file = out_dir / f"{name}.net.xml"
    intermediate = out_dir / f"{name}.routes0.net.xml"
    netconvert(osm_file, intermediate, PASS1_TLS, case.get("clip"))
    keep = keep_list(intermediate, case["names"])
    if not keep:
        raise SystemExit(f"{name}: no target arterials found in the extract")
    netconvert(osm_file, net_file, ["--keep-edges.explicit", ",".join(keep), *FINAL_TLS_FLAGS], case.get("clip"))

    # Pass 3 (post-fix, in place): keep the signals at the target crossings —
    # the junctions with the most approaches (the 4 arms of the 2x2, 9 of the
    # 3x3) — and unset the leftover OSM tags on 1–2-approach fragment nodes.
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    tls_nodes = [n for n in net.getNodes() if n.getType() == "traffic_light"]
    strong = {n.getID() for n in tls_nodes if len(n.getIncoming()) + len(n.getOutgoing()) >= 6}
    weak = sorted(n.getID() for n in tls_nodes if n.getID() not in strong)
    if weak:
        run([
            binary("netconvert"),
            "--sumo-net-file", str(net_file),
            "--tls.unset", ",".join(weak),
            "--output-file", str(net_file),
        ])
        print(f"{name}: kept {len(strong)} signals, unset {len(weak)} fragment signals")

    intermediate.unlink()
    print(f"{name}: kept {len(keep)} edges -> {net_file}")
    return net_file


def main() -> None:
    for name, case in (("sf_mission_2x2", MISSION_2X2), ("sf_mission_3x3", MISSION_3X3)):
        build(case, name)


if __name__ == "__main__":
    main()
