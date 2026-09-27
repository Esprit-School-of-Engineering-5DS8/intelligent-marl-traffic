"""Two sumo-gui windows side by side, same demand and events, two controllers.

Default: the real district at peak with emergency vehicles, fixed-time signals (the
status quo) on the left and COOP-FULL on the right. Record the screen. For the strongest
classical controller use ``--left mp``, or ``--left ev_rule_mp`` for Max-Pressure with
emergency-vehicle preemption (report, section 8.2).

    python scripts/demo_side_by_side.py [--left ft] [--right coop_full]
        [--checkpoint results/checkpoints/coop_full/real_district/seed1.zip]
        [--net real_district] [--demand peak] [--scenarios emergency] [--seed 3]

Display only (the simulation is unchanged): vehicles and pedestrians are drawn as shapes
in one colour per type - cars blue-grey, buses amber, emergency vehicles (ambulances)
white with a green cross, the accident vehicle magenta, pedestrians cyan - with a legend naming the
controller in each window. The view opens 300 m wide around the signals (``--view-width``);
zoom and pan with the mouse. ``--follow-ev`` makes the camera follow each emergency
vehicle (ids ``ev_0``, ``ev_1``...) from departure to arrival, in both windows.
``--snapshot-at 900 1800`` saves screenshots of both windows at those simulation times
(``results/tmp/demo/``), e.g. for the report.

``--headless`` runs both controllers without windows (checks the setup).
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

from cotraffic.controllers.registry import BASELINES

DEMO_DIR = Path(__file__).resolve().parents[1] / "results" / "tmp" / "demo"

# RGB 0-255, chosen for contrast on dark roads and a light background
TYPE_STYLE = {
    "car": ((125, 140, 165), "passenger/sedan"),
    "bus": ((255, 176, 0), "bus"),
    "emergency": ((255, 255, 255), "emergency"),  # sumo-gui draws it white, green cross
    "incident": ((200, 0, 200), "passenger"),
    "DEFAULT_PEDTYPE": ((0, 190, 255), "pedestrian"),
}
EV_VIEW_WIDTH = 120.0  # metres shown while the camera follows an emergency vehicle
LEGEND = [
    ("car", "car"),
    ("bus", "bus"),
    ("emergency", "ambulance (white, green cross)"),
    ("incident", "accident vehicle"),
    ("DEFAULT_PEDTYPE", "pedestrian"),
]

SETTINGS = """<viewsettings>
    <scheme name="cotraffic demo">
        <background backgroundColor="236,236,230" showGrid="0"/>
        <vehicles vehicleMode="0" vehicleQuality="2" vehicle_minSize="1.00"
                  vehicle_exaggeration="1.60" vehicle_constantSize="0" showBlinker="1">
            <colorScheme name="given vehicle/type/route color">
                <entry color="yellow"/>
            </colorScheme>
        </vehicles>
        <persons personMode="0" personQuality="2" person_minSize="1.00"
                 person_exaggeration="4.00" person_constantSize="0">
            <colorScheme name="given person/type color">
                <entry color="yellow"/>
            </colorScheme>
        </persons>
        <junctions junctionMode="0" drawCrossingsAndWalkingareas="1"/>
    </scheme>
    <delay value="{delay}"/>
    <decal file="{legend}" screenRelative="1" centerX="{cx}" centerY="{cy}"
           width="{w}" height="{h}" layer="1000"/>
</viewsettings>
"""


def draw_legend(title: str, out: Path) -> tuple[int, int]:
    """Legend image (PNG) with the controller's name and the colour of each type."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(2.9, 1.9), dpi=100)
    ax.set_axis_off()
    fig.patch.set_facecolor((1, 1, 1, 0.88))
    ax.text(0.03, 0.93, title, fontsize=11, fontweight="bold", va="top", transform=ax.transAxes)
    for i, (vtype, label) in enumerate(LEGEND):
        y = 0.72 - i * 0.15
        rgb = [c / 255 for c in TYPE_STYLE[vtype][0]]
        box = plt.Rectangle(
            (0.04, y - 0.05), 0.09, 0.1, facecolor=rgb, edgecolor="0.4", transform=ax.transAxes
        )
        ax.add_patch(box)
        if vtype == "emergency":
            ax.text(
                0.085,
                y,
                "+",
                color="#1f7a3d",
                fontsize=10,
                fontweight="bold",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        ax.text(0.17, y, label, fontsize=9, va="center", transform=ax.transAxes)
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return 290, 190


def signal_centre(net_file: Path) -> tuple[float, float]:
    """The most central signalised junction (closest on average to the others), so that
    the view opens on a real junction even when the signals are spread out."""
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    coords = [n.getCoord()[:2] for n in net.getNodes() if n.getType() == "traffic_light"]
    return min(
        coords,
        key=lambda c: sum(((c[0] - o[0]) ** 2 + (c[1] - o[1]) ** 2) ** 0.5 for o in coords),
    )


def zoom_to(env, width_m: float, centre: tuple[float, float] | None = None) -> float:
    """Zoom until the view is ``width_m`` wide (optionally centred on ``centre``).

    The zoom unit of sumo-gui depends on the window size, which is only final once the
    window is drawn, so we measure the visible area and correct the zoom proportionally.
    """
    import time

    gui = env.conn.gui
    width = width_m
    for _ in range(6):
        if centre is not None:
            gui.setOffset("View #0", *centre)
        time.sleep(0.4)  # let the window redraw before measuring it
        (x0, _), (x1, _) = gui.getBoundary("View #0")
        width = x1 - x0
        if width <= 0 or abs(width - width_m) / width_m < 0.05:
            break
        gui.setZoom("View #0", gui.getZoom("View #0") * width / width_m)
    return width


def frame_view(env, net_file: Path, width_m: float) -> float:
    """Centre the view on the most central signal, ``width_m`` wide."""
    return zoom_to(env, width_m, signal_centre(net_file))


def view_settings(title: str, tag: str, delay: int) -> Path:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    legend = DEMO_DIR / f"legend_{tag}.png"
    w, h = draw_legend(title, legend)
    settings = DEMO_DIR / f"view_{tag}.xml"
    settings.write_text(
        SETTINGS.format(
            delay=delay,
            legend=legend.as_posix(),
            cx=w // 2 + 10,
            cy=h // 2 + 10,
            w=w,
            h=h,
        ),
        encoding="utf-8",
    )
    return settings


def style_types(env) -> None:
    """Colour and shape per vehicle type (display only)."""
    vt = env.conn.vehicletype
    known = set(vt.getIDList())
    for vtype, (rgb, shape) in TYPE_STYLE.items():
        if vtype in known:
            vt.setColor(vtype, (*rgb, 255))
            vt.setShapeClass(vtype, shape)


def run(
    method: str,
    checkpoint: str | None,
    network: str,
    demand: str,
    scenarios: list[str],
    seed: int,
    x: int,
    delay: int,
    gui: bool = True,
    quick: bool = False,
    snapshot_at: tuple[float, ...] = (),
    stop_after_snapshots: bool = False,
    view_width: float = 300.0,
    follow_ev: bool = False,
) -> None:
    from cotraffic.analysis.style import label
    from cotraffic.controllers.registry import make_controller
    from cotraffic.envs.episodes import evaluation_episode, split_scenarios
    from cotraffic.envs.traffic_env import CoTrafficEnv

    controller = make_controller(method, Path(checkpoint) if checkpoint else None)
    episode = evaluation_episode(
        network,
        demand,
        scenarios,
        seed,
        ssm=False,
        quick=quick,
        additional=controller.additional_files(network, demand),
    )
    _, runtime = split_scenarios(scenarios)
    options: list[str] = []
    hooks = list(controller.step_hooks())
    if gui:
        side = "left" if x == 0 else "right"
        settings = view_settings(f"{side}: {label(method)}", f"{side}_{method}", delay)
        options = ["--window-pos", f"{x},30", "--window-size", "940,900"]
        options += ["--gui-settings-file", str(settings)]
    env = CoTrafficEnv(
        network,
        lambda rng: episode,
        controller.agent_cfg,
        controlled=controller.controlled,
        gui=gui,
        runtime_scenarios=runtime,
        step_hooks=hooks,
        compute_observations=controller.needs_observations,
        sumo_options=options,
    )
    obs, _ = env.reset(seed=seed)
    controller.reset(env)
    reframe_until = 60.0 if gui else -1.0  # the window may be resized while it opens
    pending = sorted(snapshot_at)
    tracked: str | None = None
    if gui:
        style_types(env)
    while env.agents:
        obs, *_ = env.step(controller.act(env, obs))
        if env.now <= reframe_until:
            width = frame_view(env, episode.net_file, view_width)
            if env.now + env.delta > reframe_until:
                print(f"{method}: view {width:.0f} m wide")
        if gui and follow_ev:
            # the view is framed at view_width when following starts; while the camera
            # follows a vehicle the window is not redrawn between TraCI calls, so the zoom
            # is scaled by a fixed factor instead of being measured
            factor = view_width / EV_VIEW_WIDTH
            if tracked is not None and tracked not in env.ev_ids:  # it has arrived
                env.conn.gui.trackVehicle("View #0", "")
                env.conn.gui.setZoom("View #0", env.conn.gui.getZoom("View #0") / factor)
                frame_view(env, episode.net_file, view_width)
                tracked = None
            if tracked is None and env.ev_ids:
                tracked = sorted(env.ev_ids)[0]
                env.conn.gui.trackVehicle("View #0", tracked)
                env.conn.gui.setZoom("View #0", env.conn.gui.getZoom("View #0") * factor)
                print(f"{method}: t={env.now:.0f} s, following emergency vehicle {tracked}")
        if gui and pending and env.now >= pending[0]:
            shot = DEMO_DIR / f"{network}_{method}_t{int(pending.pop(0))}.png"
            env.conn.gui.screenshot("View #0", str(shot))
            print(f"{method}: screenshot {shot}")
            if not pending and stop_after_snapshots:
                try:  # the screenshot is written at the next step
                    env.step(controller.act(env, obs))
                except Exception as exc:  # sumo-gui may close first; the file is usually there
                    print(f"{method}: last step after the screenshot failed ({exc})")
                break
    env.close()
    print(f"{method}: finished at t={env.now:.0f} s, {env.teleports} teleports")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", default="ft")
    parser.add_argument("--right", default="coop_full")
    parser.add_argument(
        "--checkpoint", default="results/checkpoints/coop_full/real_district/seed1.zip"
    )
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--scenarios", nargs="*", default=["emergency"])
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--delay", type=int, default=40, help="ms per simulation step")
    parser.add_argument(
        "--view-width", type=float, default=300.0, help="metres shown across the window"
    )
    parser.add_argument(
        "--follow-ev", action="store_true", help="the camera follows each emergency vehicle"
    )
    parser.add_argument("--headless", action="store_true", help="no window (checks the setup)")
    parser.add_argument("--quick", action="store_true", help="short episode")
    parser.add_argument(
        "--snapshot-at", type=float, nargs="*", default=[], help="simulation times (s)"
    )
    parser.add_argument(
        "--stop-after-snapshots", action="store_true", help="close once the screenshots exist"
    )
    args = parser.parse_args()
    jobs = []
    for method, x in ((args.left, 0), (args.right, 960)):
        ckpt = None if method in BASELINES else args.checkpoint
        p = mp.Process(
            target=run,
            args=(
                method,
                ckpt,
                args.net,
                args.demand,
                args.scenarios,
                args.seed,
                x,
                args.delay,
                not args.headless,
                args.quick,
                tuple(args.snapshot_at),
                args.stop_after_snapshots,
                args.view_width,
                args.follow_ev,
            ),
        )
        p.start()
        jobs.append(p)
    for p in jobs:
        p.join()


if __name__ == "__main__":
    main()
