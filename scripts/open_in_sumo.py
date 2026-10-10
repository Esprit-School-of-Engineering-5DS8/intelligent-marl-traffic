"""Open one traffic episode in sumo-gui on its own, with no program attached to it.

Useful to explore the network and the traffic freely, including in SUMO's 3D view:
``--3d`` starts sumo-gui directly in it. Opening the 3D view later from the 2D window
(View > Open new 3D view) crashes sumo-gui on our laptop (access violation in ntdll.dll,
Windows application log), as it does while a program drives the simulation (the
side-by-side demo); started in 3D it runs normally. The 3D view shows no text labels: this
SUMO build cannot read the system font for them ("arial.ttf: file not handled"), which is
harmless. The signals run a classical program: fixed-time (Webster) by default, or
actuated control (``--controller act``). Max-Pressure and the learned agents decide from
live measurements, so they need the demo: ``scripts/demo_side_by_side.py``.

    python scripts/open_in_sumo.py [--net real_district] [--demand peak]
        [--scenarios emergency buses] [--seed 3] [--controller ft] [--quick] [--3d]

Scenarios by default: emergency vehicles and buses, plus pedestrians where the network has
sidewalks (``--net real_district_ped`` for the district with sidewalks). Colours come from
the vehicle types: cars yellow, buses blue, emergency vehicles drawn as white ambulances,
the accident vehicle magenta. The window stays open at the end.
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
        if getattr(args, "three_d", False):
            cmd += ["--osg-view", "true"]  # the 3D view from the start, see the docstring
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--scenarios", nargs="*", default=None)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--controller", choices=["ft", "act"], default="ft", help="signal program to run"
    )
    parser.add_argument("--delay", type=int, default=50, help="ms per simulation step")
    parser.add_argument("--quick", action="store_true", help="short episode")
    parser.add_argument("--3d", dest="three_d", action="store_true", help="start in SUMO's 3D view")
    args = parser.parse_args()
    if args.scenarios is None:
        from cotraffic.envs.episodes import unsupported

        args.scenarios = ["emergency", "buses"]
        if "pedestrians" not in unsupported(args.net):
            args.scenarios.append("pedestrians")
    cmd = build_command(args)
    print(
        f"sumo-gui: {args.net}, {args.demand}, {' + '.join(args.scenarios) or 'normal'}, "
        f"signals: {args.controller}{', 3D view' if args.three_d else ''}. "
        "Close the window to finish."
    )
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
