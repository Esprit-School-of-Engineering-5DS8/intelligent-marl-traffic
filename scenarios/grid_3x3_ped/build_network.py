#!/usr/bin/env python3
"""
build_network.py
Generates the 3x3 grid network WITH sidewalks and pedestrian crossings for
the S4/S5 pedestrian scenarios. Same geometry and edge ids as the baseline
net (grid_3x3), so route files and topology logic stay comparable; the only
difference is the guessed sidewalks/crossings and the resulting TLS programs
(6 phases, 24 links) which now include pedestrian signal phases.
"""

import os
import subprocess
import sys


def build_grid_network(output_file="grid3x3_ped.net.xml",
                       grid_x=3, grid_y=3, grid_length=200.0,
                       attach_length=100.0, lanes=2, speed_limit=13.89):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, output_file)

    cmd = [
        "netgenerate",
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
        f"--output-file={out_path}",
    ]

    print(f"[build_network] Generating {grid_x}x{grid_y} ped grid network...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[build_network] Error during netgenerate:", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    print(f"[build_network] Successfully generated {out_path}!")


if __name__ == "__main__":
    build_grid_network()
