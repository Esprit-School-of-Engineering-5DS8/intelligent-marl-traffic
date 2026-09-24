"""Synthetic grid networks built with SUMO's netgenerate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cotraffic.utils.proc import run
from cotraffic.utils.sumo import binary


def build_grid(cfg: dict[str, Any], protocol: dict[str, Any], net_file: Path) -> Path:
    """Build a grid of signalised 4-way intersections with fringe entry/exit links.

    netgenerate names junctions by column letter and row number (A0 is south-west)
    and fringe nodes ``left0``, ``top2`` ...; edges are named ``<from><to>``.
    """
    g = cfg["grid"]
    cmd = [
        binary("netgenerate"),
        "--grid",
        "--grid.x-number",
        g["x"],
        "--grid.y-number",
        g["y"],
        "--grid.length",
        g["length"],
        "--grid.attach-length",
        g["attach_length"],
        "--default.lanenumber",
        g["lanes"],
        "--default.speed",
        g["speed"],
        "--default-junction-type",
        "traffic_light",
        "--tls.default-type",
        "static",
        "--tls.yellow.time",
        protocol["timing"]["yellow_time"],
        "--no-turnarounds",
        "true",
        "--seed",
        "0",
        "--output-file",
        net_file,
    ]
    if cfg.get("pedestrians", False):
        cmd += ["--sidewalks.guess", "true", "--crossings.guess", "true"]
    run(cmd)
    return net_file
