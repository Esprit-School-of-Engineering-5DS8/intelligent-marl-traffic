#!/usr/bin/env python3
"""
build_network.py
Generates a 2x2 signalized grid network for SUMO using netgenerate.
All 4 intersections (A0, A1, B0, B1) are equipped with 4-way traffic lights.
"""

import os
import shutil
import subprocess
import sys

def find_netgenerate():
    """Locates netgenerate executable across Windows and Linux / WSL."""
    # Check PATH first
    found = shutil.which("netgenerate")
    if found:
        return found
    if shutil.which("netgenerate.exe"):
        return shutil.which("netgenerate.exe")

    # Check SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        for ext in ["", ".exe"]:
            candidate = os.path.join(sumo_home, "bin", f"netgenerate{ext}")
            if os.path.exists(candidate):
                return candidate

    # Common Windows install path
    win_path = r"C:\Program Files (x86)\Eclipse\Sumo\bin\netgenerate.exe"
    if os.path.exists(win_path):
        return win_path

    # Common Linux path
    linux_path = "/usr/bin/netgenerate"
    if os.path.exists(linux_path):
        return linux_path

    return "netgenerate"

def build_grid_network(
    output_file="grid2x2.net.xml",
    grid_x=2,
    grid_y=2,
    grid_length=200.0,
    attach_length=100.0,
    lanes=2,
    speed_limit=13.89  # 50 km/h in m/s
):
    """
    Executes netgenerate to build a symmetric 2x2 grid network with attached boundary edges.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, output_file)
    netgenerate_bin = find_netgenerate()

    cmd = [
        netgenerate_bin,
        "--grid",
        f"--grid.x-number={grid_x}",
        f"--grid.y-number={grid_y}",
        f"--grid.length={grid_length}",
        f"--grid.attach-length={attach_length}",
        f"--default.lanenumber={lanes}",
        f"--default.speed={speed_limit}",
        "--tls.guess=true",
        "--sidewalks.guess=true",
        "--crossings.guess=true",
        f"--output-file={out_path}"
    ]

    print(f"[build_network] Generating {grid_x}x{grid_y} grid network...")
    print(" ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        print("[build_network] Error during netgenerate:", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    print(f"[build_network] Successfully generated {out_path}!")

if __name__ == "__main__":
    build_grid_network()
