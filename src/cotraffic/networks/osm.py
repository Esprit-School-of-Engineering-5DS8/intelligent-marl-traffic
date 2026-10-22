"""Real district imported from OpenStreetMap.

The raw OSM extract is saved next to the network and versioned: OSM changes every
day, so rebuilding from the saved extract is what makes the network reproducible.
"""

from __future__ import annotations

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
    osm_file = net_file.with_name(f"{cfg['name']}.osm.xml")
    if osm.get("extract_from"):  # a variant of another network: the same saved extract
        source = osm["extract_from"]
        osm_file = net_file.parent.parent / source / f"{source}.osm.xml"
    if not osm_file.is_file():
        download_osm(osm["bbox"], osm_file)
    west, south, east, north = osm["bbox"]
    cmd = [
        binary("netconvert"),
        "--osm-files",
        osm_file,
        "--output-file",
        net_file,
        "--keep-edges.by-type",
        ",".join(f"highway.{t}" for t in osm["road_types"]),
        "--keep-edges.in-geo-boundary",
        f"{west},{south},{east},{north}",
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
