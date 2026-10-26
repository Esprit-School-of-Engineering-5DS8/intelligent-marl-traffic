"""Synthetic grid networks built with SUMO's netgenerate."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cotraffic.utils.proc import CommandError, run
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
    try:
        run(cmd)
    except (CommandError, OSError) as exc:
        if "Application Control" not in str(exc) and "WinError 4551" not in str(exc):
            raise
        try:
            _build_grid_with_netconvert(cfg, protocol, net_file)
        except (CommandError, OSError):
            raise exc
    return net_file


def _build_grid_with_netconvert(
    cfg: dict[str, Any], protocol: dict[str, Any], net_file: Path
) -> None:
    """Build the same grid through netconvert when netgenerate is blocked."""
    g = cfg["grid"]
    x, y = int(g["x"]), int(g["y"])
    length, attach = float(g["length"]), float(g["attach_length"])
    lanes, speed = int(g["lanes"]), float(g["speed"])
    cols = [chr(ord("A") + i) for i in range(x)]
    rows = list(range(y))
    nodes, edges = [], []

    for i, col in enumerate(cols):
        for row in rows:
            nodes.append(
                f'<node id="{col}{row}" x="{i * length}" y="{row * length}" '
                'type="traffic_light"/>'
            )

    fringe = {
        "left": [(-attach, row * length) for row in rows],
        "right": [(length * (x - 1) + attach, row * length) for row in rows],
        "bottom": [(i * length, -attach) for i in range(x)],
        "top": [(i * length, length * (y - 1) + attach) for i in range(x)],
    }
    for side, coords in fringe.items():
        for k, (px, py) in enumerate(coords):
            nodes.append(
                f'<node id="{side}{k}" x="{px}" y="{py}" type="priority" fringe="outer"/>'
            )

    def edge(start: str, end: str) -> None:
        lanes_xml = f'numLanes="{lanes}" speed="{speed}"'
        edges.append(f'<edge id="{start}{end}" from="{start}" to="{end}" {lanes_xml}/>')
        edges.append(f'<edge id="{end}{start}" from="{end}" to="{start}" {lanes_xml}/>')

    for i, col in enumerate(cols):
        for row in rows:
            if i + 1 < x:
                edge(f"{col}{row}", f"{cols[i + 1]}{row}")
            if row + 1 < y:
                edge(f"{col}{row}", f"{col}{row + 1}")

    for i, col in enumerate(cols):
        edge(f"bottom{i}", f"{col}0")
        edge(f"top{i}", f"{col}{y - 1}")
    for row in rows:
        edge(f"left{row}", f"{cols[0]}{row}")
        edge(f"right{row}", f"{cols[-1]}{row}")

    with tempfile.TemporaryDirectory(prefix="cotraffic-grid-") as tmp:
        node_file = Path(tmp) / "grid.nod.xml"
        edge_file = Path(tmp) / "grid.edg.xml"
        node_file.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<nodes>\n'
            + "\n".join(nodes)
            + "\n</nodes>\n",
            encoding="utf-8",
        )
        edge_file.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<edges>\n'
            + "\n".join(edges)
            + "\n</edges>\n",
            encoding="utf-8",
        )
        cmd = [
            binary("netconvert"),
            "--node-files",
            node_file,
            "--edge-files",
            edge_file,
            "--output-file",
            net_file,
            "--no-turnarounds",
            "true",
            "--default-junction-type",
            "traffic_light",
            "--tls.default-type",
            "static",
            "--tls.yellow.time",
            protocol["timing"]["yellow_time"],
            "--seed",
            "0",
        ]
        if cfg.get("pedestrians", False):
            cmd += [
                "--sidewalks.guess",
                "true",
                "--sidewalks.guess.from-permissions",
                "true",
                "--crossings.guess",
                "true",
                "--walkingareas",
                "true",
            ]
        run(cmd)
