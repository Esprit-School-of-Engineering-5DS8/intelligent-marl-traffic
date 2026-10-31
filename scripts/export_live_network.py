"""Export the geometry the Live Map 3D environment renders.

For each configured SF grid network, writes
``frontend/public/data/<name>.network.json`` with:
- roads: center-line polylines + per-lane geometry (SUMO net coordinates converted to WGS84)
- junctions: signalised junction centers in WGS84
- bounds: net bounds in WGS84

Coordinates come straight from the converted net (netconvert output), so the
rendered layout is the real simulation layout, projected onto the Mapbox tiles.

Usage: python scripts/export_live_network.py [sf_mission_2x2 sf_mission_3x3]
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "public" / "data"
DEFAULT_NAMES = ["sf_mission_2x2", "sf_mission_3x3"]
LATEX, LONEX = 6371000.0, 6371000.0  # scale factors (meters -> degrees approx on roads)


def sumo_to_wgs84(x: float, y: float, netOffset) -> tuple[float, float]:
    """SUMO coordinates are (utm_offset applied); adding the netOffset restores UTM."""
    import pyproj

    utm_x, utm_y = x - netOffset[0], y - netOffset[1]
    transformer = _transformer()
    lon, lat = transformer.transform(utm_x, utm_y)
    return round(lon, 7), round(lat, 7)


_TRANSFORMER = None


def _transformer():
    global _TRANSFORMER
    if _TRANSFORMER is None:
        import pyproj

        _TRANSFORMER = pyproj.Transformer.from_crs("EPSG:32610", "EPSG:4326", always_xy=True)
    return _TRANSFORMER


def export(name: str) -> None:
    net_file = ROOT / "sumo_files" / name / f"{name}.net.xml"
    if not net_file.is_file():
        raise SystemExit(f"{name}: {net_file} not found — run the network build first")

    tree = ET.parse(net_file)
    root = tree.getroot()
    location = root.find("location")
    netOffset = [float(v) for v in location.get("netOffset").split(",")]

    import sumolib

    net = sumolib.net.readNet(str(net_file))
    convBoundary = net.getBoundary()  # (xmin, ymin, xmax, ymax)

    street_names = {}
    for _, elem in ET.iterparse(net_file, events=("end",)):
        if elem.tag == "edge" and elem.get("name"):
            street_names[elem.get("id")] = elem.get("name")

    roads, signals = [], []
    for edge in net.getEdges():
        if edge.getID().startswith(":") or edge.isSpecial() if hasattr(edge, "isSpecial") else False:
            continue
        shape = [sumo_to_wgs84(*p, netOffset) for p in edge.getShape()]
        if len(shape) < 2:
            continue
        roads.append({
            "id": edge.getID(),
            "street": street_names.get(edge.getID(), ""),
            "lanes": edge.getLaneNumber(),
            "speed": round(edge.getSpeed(), 1),
            "shape": shape,
        })

    for node in net.getNodes():
        if node.getType() != "traffic_light":
            continue
        lon, lat = sumo_to_wgs84(*node.getCoord(), netOffset)
        signals.append({"id": node.getID(), "lonlat": [lon, lat], "arms": len(node.getIncoming())})

    conv = [sumo_to_wgs84(c, convBoundary[1], netOffset)[0] for c in (convBoundary[0], convBoundary[2])]
    lat_min = sumo_to_wgs84(convBoundary[0], convBoundary[1], netOffset)[1]
    lat_max = sumo_to_wgs84(convBoundary[0], convBoundary[3], netOffset)[1]

    payload = {
        "name": name,
        "bounds": {
            "west": min(conv), "east": max(conv), "south": lat_min, "north": lat_max,
        },
        "roads": roads,
        "signals": signals,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{name}.network.json"
    out_file.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"{name}: {len(roads)} roads, {len(signals)} signals -> {out_file}")


if __name__ == "__main__":
    names = sys.argv[1:] or DEFAULT_NAMES
    for name in names:
        export(name)
