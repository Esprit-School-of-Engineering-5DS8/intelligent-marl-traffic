"""Open one traffic episode in sumo-gui on its own, with no program attached to it.

Useful to explore the network and the traffic freely, including SUMO's experimental 3D
view, which can crash sumo-gui while a program drives it step by step (as the side-by-side
demo does). The signals run a classical program: fixed-time (Webster) by default, or
actuated control (``--controller act``). Max-Pressure and the learned agents decide from
live measurements, so they need the demo: ``scripts/demo_side_by_side.py``.

    python scripts/open_in_sumo.py [--net real_district] [--demand peak]
        [--scenarios emergency buses] [--seed 3] [--controller ft] [--quick]

Colours come from the vehicle types: cars yellow, buses blue, emergency vehicles drawn as
white ambulances, the accident vehicle magenta. The window stays open at the end.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1] / "results" / "tmp" / "demo"

SETTINGS = """<viewsettings>
    <scheme name="cotraffic explore">
        <background backgroundColor="236,236,230" showGrid="0"/>
        <vehicles vehicleMode="0" vehicleQuality="2" vehicle_minSize="1.00"
                  vehicle_exaggeration="1.60" vehicle_constantSize="0" showBlinker="1"/>
        <persons personMode="0" personQuality="2" person_minSize="1.00"
                 person_exaggeration="4.00" person_constantSize="0"/>
        <junctions junctionMode="0" drawCrossingsAndWalkingareas="1"/>
    </scheme>
    <delay value="{delay}"/>
</viewsettings>
"""


def build_command(args: argparse.Namespace, gui: bool = True) -> list[str]:
    from cotraffic import config
    from cotraffic.controllers.registry import make_controller
    from cotraffic.envs.episodes import evaluation_episode
    from cotraffic.envs.simulation import sumo_command

    controller = make_controller(args.controller)
    episode = evaluation_episode(
        args.net,
        args.demand,
        args.scenarios,
        args.seed,
        ssm=False,
        quick=args.quick,
        additional=controller.additional_files(args.net, args.demand),
    )
    cmd = sumo_command(episode, config.load_protocol(), gui=gui)
    if gui:
        cmd = cmd[: cmd.index("--quit-on-end")]  # keep the window open at the end
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        settings = DEMO_DIR / "explore_view.xml"
        settings.write_text(SETTINGS.format(delay=args.delay), encoding="utf-8")
        cmd += ["--gui-settings-file", str(settings)]
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--scenarios", nargs="*", default=["emergency", "buses"])
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--controller", choices=["ft", "act"], default="ft", help="signal program to run"
    )
    parser.add_argument("--delay", type=int, default=50, help="ms per simulation step")
    parser.add_argument("--quick", action="store_true", help="short episode")
    args = parser.parse_args()
    cmd = build_command(args)
    print(
        f"sumo-gui: {args.net}, {args.demand}, {' + '.join(args.scenarios) or 'normal'}, "
        f"signals: {args.controller}. Close the window to finish."
    )
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
