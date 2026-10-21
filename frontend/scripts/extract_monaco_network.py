#!/usr/bin/env python3
"""
extract_monaco_network.py
Extracts the Monaco MoST road network from scenarios/monaco/in/most.net.xml
into a compact WGS84 GeoJSON Consumed by the Mapbox GL 3D dashboard.

Output: frontend/public/monaco-network.json
{
  "bbox": [lon_min, lat_min, lon_max, lat_max],
  "edges": [ {"id": str, "from": str, "to": str, "lanes": int,
              "speed": float, "oneway": true, "coords": [[lon,lat], ...]} ],
  "junctions": [ {"id": str, "tls": bool, "coords": [lon, lat]} ],
}

Run from the repo root:
  python frontend/scripts/extract_monaco_network.py
Author: Hazem Mrad — Simulation & Environment Lead (5DS8)
"""

import json
import math
import os
import sys
import xml.etree.ElementTree as ET

try:
    from pyproj import Transformer
except ImportError:
    print("pyproj is required: pip install pyproj", file=sys.stderr)
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NET_PATH = os.path.join(ROOT, "scenarios", "monaco", "in", "most.net.xml")
OUT_PATH = os.path.join(ROOT, "frontend", "public", "monaco-network.json")

PRECISION = 5


def parse_offset_and_proj(location):
    offset = tuple(float(v) for v in location.get("netOffset", "0,0").split(","))
    proj = location.get("projParameter", "")
    return offset, proj


def build_transformer(proj):
    # SUMO writes e.g. "+proj=utm +zone=32 +ellps=WGS84 ..." (no +type=crs),
    # which recent pyproj rejects. Patch it into an EPSG code when possible.
    if "utm" in proj:
        zone = int(proj.split("+zone=")[1].split()[0])
        south = "south" in proj
        epsg = (32700 if south else 32600) + zone
        return Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    if "latlon" in proj or "lonlat" in proj:
        return None
    if "proj=" in proj:
        patched = proj
        if "+no_defs" in patched and "+type=crs" not in patched:
            patched = patched.replace("+no_defs", "+type=crs +no_defs")
        return Transformer.from_crs(patched, "EPSG:4326", always_xy=True)
    raise ValueError(f"Unsupported projParameter: {proj!r}")


class Geo:
    def __init__(self, transformer, offset):
        self.tf = transformer
        self.ox, self.oy = offset
        self._cache = {}

    def to_lonlat(self, x, y):
        key = (round(x, 3), round(y, 3))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        gx, gy = x - self.ox, y - self.oy
        if self.tf is None:
            out = (round(gx, PRECISION), round(gy, PRECISION))
        else:
            lon, lat = self.tf.transform(gx, gy)
            out = (round(lon, PRECISION), round(lat, PRECISION))
        self._cache[key] = out
        return out


def parse_shape(shape, geo, drop_last=False):
    points = []
    for token in shape.split():
        xs, ys = token.split(",")[:2]
        points.append(geo.to_lonlat(float(xs), float(ys)))
    if drop_last and len(points) > 2:
        points = points[:-1]
    return points


def main():
    if not os.path.exists(NET_PATH):
        print(f"Network not found: {NET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {NET_PATH} ...")
    tree = ET.iterparse(NET_PATH, events=("end",))
    location = None
    edges = []
    junctions = []

    for event, elem in tree:
        tag = elem.tag
        if tag == "location":
            location = elem
        elif tag == "edge":
            if elem.get("function") in ("internal", "crossing", "walkingarea"):
                elem.clear()
                continue
            lanes = elem.findall("lane")
            if not lanes:
                elem.clear()
                continue
            lane0 = lanes[0]
            shape_raw = lane0.get("shape")
            allow = lane0.get("allow")
            disallow = lane0.get("disallow") or ""
            # Keep edges that permit motor vehicles; skip footpaths.
            allowed = set(allow.split()) if allow else None
            if allowed is not None and not (allowed - {"pedestrian"}):
                elem.clear()
                continue
            disallowed = set(disallow.split())
            if "all" in disallowed or "passenger" in disallowed and not allowed:
                elem.clear()
                continue
            edge = {
                "id": elem.get("id"),
                "from": elem.get("from"),
                "to": elem.get("to"),
                "lanes": len(lanes),
                "speed": round(float(lane0.get("speed", "13.9")), 2),
                "type": elem.get("type", ""),
            }
            edges.append((edge, shape_raw))
            elem.clear()
        elif tag == "junction":
            jtype = elem.get("type", "dead_end")
            if jtype == "internal":
                elem.clear()
                continue
            x, y = float(elem.get("x", "nan")), float(elem.get("y", "nan"))
            if math.isnan(x) or math.isnan(y):
                elem.clear()
                continue
            junctions.append(
                {"id": elem.get("id"), "tls": jtype == "traffic_light", "x": x, "y": y}
            )
            elem.clear()

    if location is None:
        print("No <location> element found — cannot georeference network.", file=sys.stderr)
        sys.exit(1)

    offset, proj = parse_offset_and_proj(location)
    geo = Geo(build_transformer(proj), offset)

    print(f"Georeferencing {len(edges)} edges, {len(junctions)} junctions ...")
    out_edges = []
    lons, lats = [], []
    for edge, shape_raw in edges:
        if shape_raw:
            coords = parse_shape(shape_raw, geo)
        else:
            coords = None
        if coords is None or len(coords) < 2:
            continue
        for lon, lat in coords:
            lons.append(lon)
            lats.append(lat)
        out_edges.append(
            {
                "id": edge["id"],
                "from": edge["from"],
                "to": edge["to"],
                "lanes": edge["lanes"],
                "speed": edge["speed"],
                "c": coords,
            }
        )

    out_junctions = []
    junction_index = {}
    for junction in junctions:
        lon, lat = geo.to_lonlat(junction["x"], junction["y"])
        junction_index[junction["id"]] = [lon, lat]
        if junction["tls"]:
            out_junctions.append({"id": junction["id"], "tls": True, "c": [lon, lat]})
            lons.append(lon)
            lats.append(lat)

    data = {
        "name": "Monaco MoST (SUMO Traffic Scenario, Codeca & Haerri, VNC 2017)",
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "edges": out_edges,
        "junctions": out_junctions,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))

    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"Wrote {OUT_PATH}: {len(out_edges)} edges, {len(out_junctions)} TLS junctions, {size_mb:.2f} MB")
    print(f"bbox: {data['bbox']}")


if __name__ == "__main__":
    main()
