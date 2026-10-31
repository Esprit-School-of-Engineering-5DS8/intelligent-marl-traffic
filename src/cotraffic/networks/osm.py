"""Real district imported from OpenStreetMap.

The raw OSM extract is saved next to the network and versioned: OSM changes every
day, so rebuilding from the saved extract is what makes the network reproducible.
"""

from __future__ import annotations

import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cotraffic.utils.proc import run
from cotraffic.utils.sumo import binary

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def download_osm(bbox: list[float], out_file: Path, attempts: int = 6) -> Path:
    """Download all ``highway`` ways intersecting ``bbox`` = [west, south, east, north]."""
    west, south, east, north = bbox
    query = (
        f'[out:xml][timeout:120];(way["highway"]({south},{west},{north},{east}););(._;>;);out body;'
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for attempt in range(attempts):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        request = urllib.request.Request(url, data=data, headers={"User-Agent": "cotraffic"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = response.read()
            if b"<osm" not in payload[:500]:
                raise ValueError("Overpass answer is not an OSM document")
            out_file.write_bytes(payload)
            return out_file
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            last_error = err
            time.sleep(10 * (attempt + 1))  # Overpass rate limits bursts of requests
    raise RuntimeError(f"OSM download failed after {attempts} attempts: {last_error}")


def build_osm(cfg: dict[str, Any], protocol: dict[str, Any], net_file: Path) -> Path:
    osm = cfg["osm"]
    if osm.get("keep_names"):
        return _build_corridor(cfg, osm, protocol, net_file)
    osm_file = net_file.with_name(f"{cfg['name']}.osm.xml")
    if osm.get("extract_from"):  # a variant of another network: the same saved extract
        source = osm["extract_from"]
        osm_file = net_file.parent.parent / source / f"{source}.osm.xml"
    if not osm_file.is_file():
        download_osm(osm["bbox"], osm_file)
    west, south, east, north = osm["bbox"]
    geo_boundary = f"{west},{south},{east},{north}"
    if osm.get("boundary_polygon"):
        poly_p = Path(osm["boundary_polygon"])
        if not poly_p.is_absolute():
            poly_p = Path.cwd() / poly_p
        if poly_p.is_file():
            geo_boundary = poly_p.read_text().strip()
    cmd = [
        binary("netconvert"),
        "--osm-files",
        osm_file,
        "--output-file",
        net_file,
        "--keep-edges.by-type",
        ",".join(f"highway.{t}" for t in osm["road_types"]),
        "--keep-edges.in-geo-boundary",
        geo_boundary,
        "--keep-edges.components",
        "1",
        "--remove-edges.isolated",
        "true",
        "--geometry.remove",
        "true",
        "--roundabouts.guess",
        "true",
        "--junctions.join",
        "true",
        "--junctions.join-dist",
        osm.get("join_dist_m", 15),
        "--junctions.corner-detail",
        "5",
        "--edges.join",
        "true",
        "--tls.guess-signals",
        "true",
        "--tls.guess-signals.dist",
        osm.get("signal_dist_m", 25),
        "--tls.join",
        "true",
        "--tls.join-dist",
        osm.get("tls_join_dist_m", 30),
        "--tls.discard-simple",
        "true",
        "--tls.default-type",
        "static",
        "--tls.yellow.time",
        protocol["timing"]["yellow_time"],
        "--no-turnarounds.tls",
        "true",
        "--output.street-names",
        "true",
        "--seed",
        "0",
    ]
    if osm.get("guess_tls", False):
        cmd += ["--tls.guess", "true", "--tls.guess.threshold", osm.get("guess_threshold", 69)]
    # explicit corrections of the OSM signal tags (junction ids of the joined network)
    if osm.get("tls_set"):
        cmd += ["--tls.set", ",".join(str(j) for j in osm["tls_set"])]
    if osm.get("tls_unset"):
        cmd += ["--tls.unset", ",".join(str(j) for j in osm["tls_unset"])]
    if cfg.get("pedestrians", False):
        cmd += ["--sidewalks.guess", "true", "--crossings.guess", "true"]
        # netconvert guesses sidewalks, and crossings at junctions, only up to 50 km/h by default
        if osm.get("sidewalks_max_speed_kmh"):
            speed = float(osm["sidewalks_max_speed_kmh"]) / 3.6
            cmd += [
                "--sidewalks.guess.max-speed",
                speed,
                "--crossings.guess.speed-threshold",
                speed,
            ]
    run(cmd)
    return net_file


def _build_corridor(
    cfg: dict[str, Any], osm: dict[str, Any], protocol: dict[str, Any], net_file: Path
) -> Path:
    """Skeleton network of a few real streets of the extract.

    ``osm.keep_names`` lists the street names that survive (e.g. the six
    arterials of a City-grid 3x3) and ``osm.corridor_crossings`` the lon/lat
    pairs of the target junctions. The filtering happens at the OSM level: a
    pruned copy of the extract loses every way that is not one of the target
    streets or that lies outside the corridor rectangle, plus every
    traffic_signals tag far from the target crossings. netconvert then only
    converts what survives, so no keep/remove edge-flag gymnastics is needed.
    """
    name = cfg["name"]
    keep_names = set(osm["keep_names"])
    crossings = [[c[0], c[1]] for c in osm["corridor_crossings"]]
    margin_lon = osm.get("corridor_margin_lon", 0.0006)  # ~55 m
    margin_lat = osm.get("corridor_margin_lat", 0.0009)  # ~100 m
    corridor = [
        min(c[0] for c in crossings) - margin_lon,
        min(c[1] for c in crossings) - margin_lat,
        max(c[0] for c in crossings) + margin_lon,
        max(c[1] for c in crossings) + margin_lat,
    ]

    osm_file = net_file.with_name(f"{name}.osm.xml")
    if osm.get("extract_from"):
        source = osm["extract_from"]
        osm_file = net_file.parent.parent / source / f"{source}.osm.xml"
    if not osm_file.is_file():
        download_osm(osm["bbox"], osm_file)

    pruned = _prune_corridor(
        osm_file, net_file.with_name(f"{name}.corridor.osm.xml"), keep_names, crossings, corridor
    )
    pruned = _prune_signal_tags(pruned, pruned, crossings)
    cmd = [
        binary("netconvert"),
        "--osm-files", str(pruned),
        "--output-file", str(net_file),
        "--keep-edges.by-type", ",".join(f"highway.{t}" for t in osm["road_types"]),
        "--keep-edges.in-geo-boundary", ",".join(f"{c:.5f}" for c in corridor),
        "--keep-edges.components", "1",
        "--remove-edges.isolated", "true",
        "--geometry.remove", "true",
        "--junctions.join", "true",
        "--junctions.join-dist", str(osm.get("join_dist_m", 15)),
        "--junctions.corner-detail", "5",
        "--edges.join", "true",
        "--roundabouts.guess", "true",
        "--tls.guess-signals", "true",
        "--tls.guess-signals.dist", str(osm.get("signal_dist_m", 25)),
        "--tls.join", "true",
        "--tls.join-dist", str(osm.get("tls_join_dist_m", 30)),
        "--tls.discard-simple", "true",
        "--tls.default-type", "static",
        "--tls.yellow.time", str(protocol["timing"]["yellow_time"]),
        "--no-turnarounds.tls", "true",
        "--output.street-names", "true",
        "--seed", "0",
    ]
    if osm.get("guess_tls", False):
        cmd += ["--tls.guess", "true", "--tls.guess.threshold", str(osm.get("guess_threshold", 69))]
    if cfg.get("pedestrians", False):
        cmd += ["--sidewalks.guess", "true", "--crossings.guess", "true"]
    run(cmd)

    import sumolib  # noqa: PLC0415

    net = sumolib.net.readNet(str(net_file))
    signals = len([n for n in net.getNodes() if n.getType() == "traffic_light"])
    print(f"{name}: {signals} signalised junctions over {len(net.getEdges())} edges")
    return net_file


def _prune_corridor(
    osm_file: Path, out_file: Path, keep_names: set[str], crossings: list[list[float]], corridor: list[float]
) -> Path:
    """Copy the extract keeping the target-street ways that enter the corridor."""
    import xml.etree.ElementTree as ET

    tree = ET.parse(str(osm_file))
    root = tree.getroot()
    cos = math.cos(math.radians(sum(c[1] for c in crossings) / len(crossings)))
    near = 70.0  # slack outside the corridor borders, in metres

    corner = [
        [corridor[0] - near / (111320 * cos), corridor[1] - near / 110540],
        [corridor[2] + near / (111320 * cos), corridor[3] + near / 110540],
    ]
    points = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.findall("node")}

    def touches(way) -> bool:
        for point in way.findall("nd"):
            xy = points.get(point.get("ref"))
            if xy and corner[0][0] <= xy[0] <= corner[1][0] and corner[0][1] <= xy[1] <= corner[1][1]:
                return True
        return False

    dropped = 0
    for way in list(root.findall("way")):
        nm = [t.get("v") for t in way.findall("tag") if t.get("k") == "name"]
        if not nm or nm[0] not in keep_names or not touches(way):
            root.remove(way)
            dropped += 1
    ET.indent(tree)
    tree.write(str(out_file), encoding="UTF-8", xml_declaration=True)
    print(f"{out_file.name}: dropped {dropped} ways off the corridor")
    return out_file


def _prune_signal_tags(osm_file: Path, out_file: Path, crossings: list[list[float]]) -> Path:
    """Copy the extract, dropping every traffic_signals tag far from a crossing."""
    import xml.etree.ElementTree as ET

    tree = ET.parse(str(osm_file))
    root = tree.getroot()
    lat_ref = sum(c[1] for c in crossings) / len(crossings)
    cos = math.cos(math.radians(lat_ref))
    radius = 60.0  # metres: signal tags hang a few metres off the junction

    pruned = 0
    for node in root.iter("node"):
        tags = node.findall("tag")
        if not tags:
            continue
        lon, lat = float(node.get("lon")), float(node.get("lat"))
        for tag in list(tags):
            if tag.get("k") == "highway" and tag.get("v") == "traffic_signals":
                far = True
                for clon, clat in crossings:
                    dx = (lon - clon) * 111320 * cos
                    dy = (lat - clat) * 110540
                    if dx * dx + dy * dy <= radius * radius:
                        far = False
                        break
                if far:
                    tags.remove(tag)
                    pruned += 1
    if pruned:
        ET.indent(tree)
        tree.write(str(out_file), encoding="UTF-8", xml_declaration=True)
    return out_file
