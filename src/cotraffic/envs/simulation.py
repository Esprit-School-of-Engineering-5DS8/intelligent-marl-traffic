"""Starting and stopping one SUMO simulation.

With libsumo the simulation runs inside the Python process (fast, one simulation
per process); with TraCI it runs as a separate process (needed for sumo-gui).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cotraffic.demand.generator import RouteBundle
from cotraffic.utils.sumo import backend, binary, use_libsumo

_labels = itertools.count()


@dataclass
class Episode:
    """Everything that defines one simulation run besides the controller."""

    net_file: Path
    bundle: RouteBundle
    end_time: float
    sumo_seed: int
    measure_from: float = 0.0  # start of the measured window (after warm-up)
    measure_to: float | None = None  # end of the measured window
    output_dir: Path | None = None  # SUMO writes tripinfo/summary/statistics/SSM here
    ssm: bool = False
    additional: tuple[Path, ...] = ()  # e.g. the signal programs of a baseline
    info: dict[str, Any] = field(default_factory=dict)


def sumo_command(ep: Episode, protocol: dict[str, Any], gui: bool = False) -> list[str]:
    s = protocol["sumo"]
    additional = [*ep.bundle.additional_files, *ep.additional]
    cmd = [
        binary("sumo-gui" if gui else "sumo"),
        "--net-file",
        str(ep.net_file),
        "--route-files",
        ",".join(str(p) for p in ep.bundle.route_files),
        "--additional-files",
        ",".join(str(p) for p in additional),
        "--begin",
        "0",
        "--end",
        str(ep.end_time),
        "--step-length",
        str(s["step_length"]),
        "--seed",
        str(ep.sumo_seed),
        "--time-to-teleport",
        str(s["time_to_teleport"]),
        "--waiting-time-memory",
        str(s["waiting_time_memory"]),
        "--max-depart-delay",
        str(s["max_depart_delay"]),
        "--no-step-log",
        "true",
        "--no-warnings",
        "true",
        "--duration-log.disable",
        "true",
    ]
    if ep.output_dir is not None:
        out = Path(ep.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        cmd += [
            "--tripinfo-output",
            str(out / "tripinfo.xml"),
            "--tripinfo-output.write-unfinished",
            "true",
            "--device.emissions.probability",
            "1",
            "--summary-output",
            str(out / "summary.xml"),
            "--statistic-output",
            str(out / "statistics.xml"),
            "--emergencydecel.warning-threshold",
            str(s["hard_braking_fraction"]),
            "--log",
            str(out / "sumo.log"),
        ]
        if ep.ssm:
            cmd += [
                "--device.ssm.probability",
                "1",
                "--device.ssm.measures",
                s["ssm"]["measures"],
                "--device.ssm.thresholds",
                s["ssm"]["thresholds"],
                "--device.ssm.range",
                str(s["ssm"]["range"]),
                "--device.ssm.file",
                str(out / "ssm.xml"),
            ]
    if gui:
        cmd += ["--start", "true", "--quit-on-end", "true"]
    return cmd


class Simulation:
    """Owns the connection to one running SUMO instance."""

    def __init__(self, gui: bool = False):
        self.gui = gui
        self.libsumo = use_libsumo(gui)
        self.module = backend(gui)
        self.conn = None
        self.label: str | None = None

    def start(self, cmd: list[str]):
        self.close()
        if self.libsumo:
            self.module.start(cmd)
            self.conn = self.module
        else:
            self.label = f"cotraffic_{next(_labels)}"
            self.module.start(cmd, label=self.label)
            self.conn = self.module.getConnection(self.label)
        return self.conn

    def close(self) -> None:
        if self.conn is None:
            return
        try:
            self.conn.close()
        finally:
            self.conn = None
            self.label = None
