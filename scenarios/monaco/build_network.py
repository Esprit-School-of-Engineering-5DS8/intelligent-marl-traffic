#!/usr/bin/env python3
"""
build_network.py (scenarios/monaco)
Phase 3: Downloads real-world OpenStreetMap (OSM) data for Monaco (Port Hercule & Monte Carlo)
and compiles it into a full SUMO road network equipped with:
- Real street geometries and speed limits
- Multi-modal infrastructure: sidewalks, crossings, and signalized junctions
- Roundabout and intersection joining
"""

import os
import sys
import shutil
import subprocess
import urllib.request


def find_netconvert():
    """Locates netconvert executable across Windows and Linux / WSL."""
    found = shutil.which("netconvert")
    if found:
        return found
    if shutil.which("netconvert.exe"):
        return shutil.which("netconvert.exe")

    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        for ext in ["", ".exe"]:
            candidate = os.path.join(sumo_home, "bin", f"netconvert{ext}")
            if os.path.exists(candidate):
                return candidate

    win_path = r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe"
    if os.path.exists(win_path):
        return win_path

    return "netconvert"


def download_monaco_osm(osm_path: str):
    """
    Downloads central Monaco road network via Overpass API:
    Bounding box covers Port Hercule, Monte Carlo, and major arterial avenues.
    """
    if os.path.exists(osm_path) and os.path.getsize(osm_path) > 100000:
        print(f"[build_network] Using cached OSM data: {osm_path}")
        return

    url = "https://api.openstreetmap.org/api/0.6/map?bbox=7.418,43.732,7.428,43.740"
    print("[build_network] Downloading real Monaco road network from OpenStreetMap API...")
    req = urllib.request.Request(url, headers={"User-Agent": "SUMO-Monaco-Builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    with open(osm_path, "wb") as f:
        f.write(data)
    print(f"[build_network] Successfully saved {len(data):,} bytes of OSM data to {osm_path}!")


def compile_monaco_network(
    osm_file="monaco.osm.xml",
    output_net="monaco.net.xml",
):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    osm_path = os.path.join(script_dir, osm_file)
    net_path = os.path.join(script_dir, output_net)

    # 1. Fetch OSM data if needed
    download_monaco_osm(osm_path)

    # 2. Run netconvert
    netconvert_bin = find_netconvert()
    cmd = [
        netconvert_bin,
        "--osm-files", osm_path,
        "--output-file", net_path,
        "--geometry.remove", "true",
        "--roundabouts.guess", "true",
        "--ramps.guess", "true",
        "--junctions.join", "true",
        "--tls.guess", "true",
        "--tls.join", "true",
        "--tls.default-type", "static",
        "--sidewalks.guess", "true",
        "--crossings.guess", "true",
        "--no-warnings", "true",
    ]

    print("[build_network] Compiling OSM to SUMO network via netconvert...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[build_network] netconvert error:", res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    print(f"[build_network] Successfully compiled real-world Monaco network: {net_path}!")


if __name__ == "__main__":
    compile_monaco_network()
