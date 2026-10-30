"""Two sumo-gui windows side by side, same demand and events, two controllers.

Default: the real district at peak with emergency vehicles and buses, fixed-time signals (the
status quo) on the left and COOP-FULL on the right. Record the screen. For the strongest
classical controller use ``--left mp``, or ``--left ev_rule_mp`` for Max-Pressure with
emergency-vehicle preemption (report, section 8.2).

    python scripts/demo_side_by_side.py [--left ft] [--right coop_full]
        [--checkpoint results/checkpoints/coop_full/real_district/seed1.zip]
        [--net real_district] [--demand peak] [--scenarios ...] [--seed 3]

Scenarios by default: emergency vehicles and buses, plus pedestrians on the networks that
have sidewalks. The district's OpenStreetMap import has almost none (FAILURES F-011);
``--net real_district_ped`` is the same district with sidewalks and crossings on every
street, for the demonstration only (not evaluated), driven by the agents trained on
real_district.

Display only (the simulation is unchanged): dark asphalt, light paving for sidewalks and
crossings, green blocks; road users drawn as detailed shapes in one colour per type - cars
light blue, buses amber, emergency vehicles (ambulances) white with a green cross, the
accident vehicle magenta, pedestrians deep blue (drawn at a constant size on the screen) -
with a legend naming the controller in each window, in the colour of its line in the live
chart (left blue, right orange). The view opens 300 m wide around the signals (``--view-width``);
zoom and pan with the mouse. ``--follow-ev`` makes the camera follow each emergency
vehicle (ids ``ev_0``, ``ev_1``...) from departure to arrival, in both windows; the
simulation fast-forwards to 30 s before the first one departs. Both windows wait for each
other at that point (or after the first minute), then run in step.
``--follow-incident`` adds the accident scenario (a vehicle stopped on one lane just before
a junction for 15 min) and puts the camera on the blocked street, in both windows; the
simulation fast-forwards to 1 min before the accident. The stopped vehicle is magenta with
its hazard lights on, inside a flashing red zone, with an ACCIDENT sign beside the road
(display only, as the colours).
``--snapshot-at 900 1800`` saves screenshots of both windows at those simulation times
(``results/tmp/demo/``), e.g. for the report.
``--only-ev ev_1`` follows that emergency vehicle only and closes each window 8 s after it
arrives, printing its time on the road; ``--record`` adds one screenshot per simulated second
while it is followed (``results/tmp/demo/record/``), which ``scripts/demo_record.py`` puts side
by side in an animated GIF. The final controller of the combined study is ``hybrid_h2``
(COOP-FULL with its training run 1, a bias of 4 towards Max-Pressure, EV-RULE pre-emption):

    python scripts/demo_side_by_side.py --left mp --right hybrid_h2 --net grid4x4
        --demand peak --scenarios emergency --seed 0 --only-ev ev_1 --ev-view-width 160
        --no-chart [--record]

A third window charts both controllers live on the same traffic (``scripts/demo_chart.py``):
headline numbers with the difference between them (mean trip time, waiting at the signals,
pedestrian waiting, ambulances, trips through the blocked street), then their course over
time, with the hour measured by the evaluation and the accident shaded; it is saved at the
end (``--no-chart`` to skip it). The two windows wait for each other every simulated minute
so that they show the same moment.

``--headless`` runs both controllers without windows (checks the setup).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import multiprocessing as mp
import time
from pathlib import Path

from demo_chart import SIDE_COLORS

from cotraffic.controllers.registry import BASELINES, CANDIDATE
from cotraffic.paths import default_checkpoint

DEMO_DIR = Path(__file__).resolve().parents[1] / "results" / "tmp" / "demo"

# Display only. RGB 0-255: three levels of lightness separate the street from the blocks -
# dark asphalt, light paving for sidewalks and crossings, a mid-light green for the blocks -
# and each road user stands out on what it moves on: light cars on the asphalt, deep blue
# pedestrians on the paving.
BACKGROUND = (207, 220, 198)
ROAD = (58, 61, 68)
SIDEWALK = (240, 235, 225)
TYPE_STYLE = {
    "car": ((160, 186, 226), "passenger/sedan"),
    "bus": ((255, 176, 0), "bus"),
    "emergency": ((255, 255, 255), "emergency"),  # sumo-gui draws it white, green cross
    "incident": ((200, 0, 200), "passenger"),
    "DEFAULT_PEDTYPE": ((0, 110, 220), "pedestrian"),
}
EV_VIEW_WIDTH = 120.0  # metres shown while the camera follows an emergency vehicle
INCIDENT_VIEW_WIDTH = 150.0  # metres shown around the accident vehicle
ACCIDENT_RED = (230, 0, 0)
HAZARD_LIGHTS = 4 | 8  # TraCI signal bits: both blinkers (hazard lights) + brake lights
LEGEND = [
    (TYPE_STYLE["car"][0], "car"),
    (TYPE_STYLE["bus"][0], "bus"),
    (TYPE_STYLE["emergency"][0], "ambulance (white, green cross)"),
    (TYPE_STYLE["incident"][0], "accident (red zone)"),
    (TYPE_STYLE["DEFAULT_PEDTYPE"][0], "pedestrian"),
    (SIDEWALK, "sidewalk, crossing"),
]

SETTINGS = """<viewsettings>
    <scheme name="cotraffic demo">
        <opengl antialiase="0" dither="0"/>
        <background backgroundColor="{background}" showGrid="0"/>
        <edges laneEdgeMode="0" laneShowBorders="1" showLinkDecals="1" showLinkRules="1">
            <colorScheme name="uniform">
                <entry color="{road}" name="road"/>
                <entry color="{sidewalk}" name="sidewalk"/>
                <entry color="192,66,44" name="bike lane"/>
                <entry color="invisible" name="green verge"/>
                <entry color="150,200,200" name="waterway"/>
                <entry color="black" name="railway"/>
                <entry color="64,0,64" name="rails on road"/>
                <entry color="92,92,92" name="no passenger"/>
                <entry color="red" name="closed"/>
                <entry color="green" name="connector"/>
                <entry color="orange" name="forbidden"/>
                <entry color="200,240,240" name="airway"/>
            </colorScheme>
        </edges>
        <vehicles vehicleMode="0" vehicleQuality="3" vehicle_minSize="1.00"
                  vehicle_exaggeration="1.60" vehicle_constantSize="0" showBlinker="1">
            <colorScheme name="given vehicle/type/route color">
                <entry color="yellow"/>
            </colorScheme>
        </vehicles>
        <persons personMode="0" personQuality="3" person_minSize="1.00"
                 person_exaggeration="2.00" person_constantSize="1">
            <colorScheme name="given person/type color">
                <entry color="yellow"/>
            </colorScheme>
        </persons>
        <junctions junctionMode="0" drawCrossingsAndWalkingareas="1">
            <colorScheme name="uniform">
                <entry color="{road}"/>
                <entry color="150,200,200" name="waterway"/>
                <entry color="invisible" name="railway"/>
                <entry color="200,240,240" name="airway"/>
            </colorScheme>
        </junctions>
    </scheme>
    <delay value="0"/>
    <decal file="{legend}" screenRelative="1" centerX="{cx}" centerY="{cy}"
           width="{w}" height="{h}" layer="1000"/>
</viewsettings>
"""


def draw_legend(title: str, colour: str, out: Path) -> tuple[int, int]:
    """Legend (PNG): the controller of the window, with the colour of its line in the live
    chart, and the colour of each road user. Drawn at twice the screen size for sharp text."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w_in, h_in = 2.9, 0.62 + 0.25 * len(LEGEND)
    fig = plt.figure(figsize=(w_in, h_in), dpi=200)
    fig.patch.set_facecolor((1, 1, 1, 0.92))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.set_xlim(0, w_in)
    ax.set_ylim(h_in, 0)  # y downwards, in inches
    ax.add_patch(plt.Rectangle((0, 0), w_in, 0.06, facecolor=colour, edgecolor="none"))
    ax.text(0.14, 0.3, title, fontsize=11, fontweight="bold", color="#0b0b0b", va="center")
    for i, (rgb, label) in enumerate(LEGEND):
        y = 0.62 + 0.25 * i
        fill = [c / 255 for c in rgb]
        ax.add_patch(
            plt.Rectangle(
                (0.14, y - 0.08), 0.3, 0.16, facecolor=fill, edgecolor="#898781", linewidth=0.6
            )
        )
        if label.startswith("ambulance"):
            ax.text(
                0.29,
                y,
                "+",
                color="#1f7a3d",
                fontsize=10,
                fontweight="bold",
                ha="center",
                va="center",
            )
        ax.text(0.56, y, label, fontsize=9, color="#0b0b0b", va="center")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return round(w_in * 100), round(h_in * 100)


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


def view_settings(title: str, colour: str, tag: str) -> Path:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    legend = DEMO_DIR / f"legend_{tag}.png"
    w, h = draw_legend(title, colour, legend)
    settings = DEMO_DIR / f"view_{tag}.xml"
    settings.write_text(
        SETTINGS.format(
            background=",".join(map(str, BACKGROUND)),
            road=",".join(map(str, ROAD)),
            sidewalk=",".join(map(str, SIDEWALK)),
            legend=legend.as_posix(),
            cx=w // 2 + 10,
            cy=h // 2 + 10,
            w=w,
            h=h,
        ),
        encoding="utf-8",
    )
    return settings


def ev_departures(episode, ev_id: str | None = None) -> list[float]:
    """Departure times of the emergency vehicles (ids ev_0, ev_1, ...) of the episode, or of
    the one named ``ev_id``."""
    import re

    pattern = re.escape(ev_id) if ev_id else r"ev_\d+"
    times: list[float] = []
    for f in episode.bundle.route_files:
        text = Path(f).read_text(encoding="utf-8")
        times += [
            float(t) for t in re.findall(rf'<vehicle id="{pattern}"[^>]*depart="([0-9.]+)"', text)
        ]
    return sorted(times)


def style_types(env) -> None:
    """Colour and shape per vehicle type (display only)."""
    vt = env.conn.vehicletype
    known = set(vt.getIDList())
    for vtype, (rgb, shape) in TYPE_STYLE.items():
        if vtype in known:
            vt.setColor(vtype, (*rgb, 255))
            vt.setShapeClass(vtype, shape)


def draw_accident_sign(out: Path) -> None:
    """Warning sign (PNG, transparent): red triangle with "!" over an ACCIDENT label."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(2.4, 2.0), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.set_xlim(0, 1.2)
    ax.set_ylim(0, 1)
    red = [c / 255 for c in ACCIDENT_RED]
    ax.add_patch(
        plt.Polygon(
            [(0.3, 0.33), (0.9, 0.33), (0.6, 0.97)],
            closed=True,
            facecolor="white",
            edgecolor=red,
            linewidth=7,
            joinstyle="round",
        )
    )
    ax.text(0.6, 0.53, "!", fontsize=34, fontweight="bold", ha="center", va="center")
    ax.text(
        0.6,
        0.13,
        "ACCIDENT",
        fontsize=17,
        fontweight="bold",
        color="white",
        ha="center",
        va="center",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": red, "edgecolor": "none"},
    )
    fig.savefig(out, transparent=True)
    plt.close(fig)


def show_accident(env, sign: Path) -> bool:
    """Red zone, warning sign and hazard lights around the stopped vehicle (display only:
    polygons and points of interest do not interact with traffic)."""
    import math

    from traci.exceptions import TraCIException

    conn = env.conn
    try:
        x, y = conn.vehicle.getPosition("incident_0")
        heading = math.radians(conn.vehicle.getAngle("incident_0"))  # 0 = north, clockwise
        conn.vehicle.setSignals("incident_0", HAZARD_LIGHTS)
    except TraCIException:
        return False  # it left the network in between
    circle = [
        (x + 11 * math.cos(k * math.pi / 12), y + 11 * math.sin(k * math.pi / 12))
        for k in range(24)
    ]
    conn.polygon.add("accident_zone", circle, (*ACCIDENT_RED, 100), fill=True, layer=5)
    conn.polygon.add(
        "accident_ring", [*circle, circle[0]], (*ACCIDENT_RED, 255), layer=5, lineWidth=1.2
    )
    # the sign stands beside the road, to the right of the direction of travel
    sx, sy = x + 17 * math.cos(heading), y - 17 * math.sin(heading)
    conn.poi.add("accident_sign", sx, sy, (255, 255, 255, 255), "accident", 6, str(sign), 22, 18)
    return True


def hide_accident(env) -> None:
    conn = env.conn
    for remove, shape in (
        (conn.polygon.remove, "accident_zone"),
        (conn.polygon.remove, "accident_ring"),
        (conn.poi.remove, "accident_sign"),
    ):
        with contextlib.suppress(Exception):  # the window may be closing
            remove(shape)


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
    sync=None,
    stats=None,
    follow_incident: bool = False,
    only_ev: str | None = None,
    record: bool = False,
    ev_view_width: float = 120.0,
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
    incident = episode.bundle.meta.get("incident")
    pedestrians = "pedestrians" in scenarios
    options: list[str] = []
    hooks = list(controller.step_hooks())
    # pacing: sumo-gui runs without its own delay; we pause after each simulated second,
    # except while fast-forwarding (TraCI cannot change the delay of the window)
    pace = {"on": True}

    def pause(env, now: float) -> None:
        if pace["on"] and delay > 0:
            time.sleep(delay / 1000)

    if gui:
        hooks.append(pause)
    accident = {"shown": False, "tries": 0}  # shown: the red zone and the sign are drawn

    def flash(env, now: float) -> None:
        if accident["shown"]:
            alpha = 120 if int(now) % 2 == 0 else 30
            with contextlib.suppress(Exception):
                env.conn.polygon.setColor("accident_zone", (*ACCIDENT_RED, alpha))

    if gui and incident:
        hooks.append(flash)
    # --only-ev: the departure and arrival of that vehicle, to the second; --record: one
    # screenshot per simulated second from the moment the camera follows it until 5 s after
    # its arrival, for scripts/demo_record.py
    rec = {"on": False, "depart": None, "arrive": None, "side": "", "dir": DEMO_DIR / "record"}

    def ev_clock(env, now: float) -> None:
        sim = env.conn.simulation
        if rec["depart"] is None and only_ev in sim.getDepartedIDList():
            rec["depart"] = now
        if rec["arrive"] is None and only_ev in sim.getArrivedIDList():
            rec["arrive"] = now

    def shoot(env, now: float) -> None:
        if rec["on"] and (rec["arrive"] is None or now <= rec["arrive"] + 5):
            shot = rec["dir"] / f"{rec['side']}_{int(now):05d}.png"
            with contextlib.suppress(Exception):
                env.conn.gui.screenshot("View #0", str(shot))

    if only_ev:
        hooks.append(ev_clock)
    if gui and record:
        hooks.append(shoot)
    # live comparison: completed trips, measured the same way for both controllers; with an
    # accident, also the trips through the blocked street that depart from 10 min before it
    # to its end (the population of the evaluation's incident metric)
    trips = {"dep": {}, "tt": [], "arrived": 0, "ev": {}, "through": set(), "aff": []}

    def count_trips(env, now: float) -> None:
        sim = env.conn.simulation
        for v in sim.getDepartedIDList():
            trips["dep"][v] = now
            if (
                incident
                and incident["start"] - 600 <= now < incident["end"]
                and not v.startswith("incident_")
                and incident["edge"] in env.conn.vehicle.getRoute(v)
            ):
                trips["through"].add(v)
        for v in sim.getArrivedIDList():
            trips["arrived"] += 1
            t0 = trips["dep"].pop(v, None)
            if t0 is not None:
                trips["tt"].append(now - t0)
                if v.startswith("ev_"):
                    trips["ev"][v] = now - t0
                if v in trips["through"]:
                    trips["aff"].append(now - t0)

    if stats is not None:
        hooks.append(count_trips)
    if gui:
        side = "left" if x == 0 else "right"
        rec["side"] = side
        if record:
            rec["dir"].mkdir(parents=True, exist_ok=True)
            for old in rec["dir"].glob(f"{side}_*"):
                old.unlink()
        colour = SIDE_COLORS[0 if x == 0 else 1]
        settings = view_settings(f"{side}: {label(method)}", colour, f"{side}_{method}")
        options = ["--window-pos", f"{x},30", "--window-size", "940,900"]
        options += ["--gui-settings-file", str(settings)]
        options += ["--error-log", str(DEMO_DIR / f"sumo_{side}_{method}.log")]
        sign = DEMO_DIR / f"accident_sign_{side}.png"
        if incident:
            draw_accident_sign(sign)
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
    framed = {"zoom": 100.0, "width": view_width}
    pending = sorted(snapshot_at)
    tracked: str | None = None
    meet_at = None  # simulation time at which both windows wait for each other
    on_incident = False  # the camera shows the blocked street
    if gui:
        meet_at = reframe_until
        targets = []
        departures = ev_departures(episode, only_ev) if follow_ev else []
        if follow_ev and not departures:
            print(f"{method}: no emergency vehicle {only_ev or ''} in this scenario "
                  "(add --scenarios emergency)")  # fmt: skip
        if departures:
            targets.append(departures[0] - 30.0)
            times = ", ".join(f"{t:.0f}" for t in departures)
            print(f"{method}: emergency vehicles depart at t = {times} s (simulation time)")
        if follow_incident and incident:
            targets.append(incident["start"] - 60.0)
            print(
                f"{method}: accident on street {incident['edge']} (lane {incident['lane']}) "
                f"from t={incident['start']:.0f} to {incident['end']:.0f} s"
            )
        if targets:
            meet_at = max(reframe_until, min(targets))
            if meet_at > reframe_until:
                print(f"{method}: fast-forward to t={meet_at:.0f} s, then normal speed")
                pace["on"] = False
    if gui:
        style_types(env)
    from traci.exceptions import FatalTraCIError, TraCIException

    try:
        while env.agents:
            obs, *_ = env.step(controller.act(env, obs))
            if env.now <= reframe_until:
                width = frame_view(env, episode.net_file, view_width)
                # the zoom at which the view measured `width`: the camera following a vehicle
                # is zoomed from it (trackVehicle may change the zoom of the window)
                framed["zoom"], framed["width"] = env.conn.gui.getZoom("View #0"), width
                if env.now + env.delta > reframe_until:
                    print(f"{method}: view {width:.0f} m wide")
            if stats is not None:
                lanes = [ln for i in env.intersections.values() for ln in i.in_lanes]
                halting = sum(env.meas.halting[ln] for ln in lanes)
                tt = trips["tt"]
                mean_tt = sum(tt) / len(tt) if tt else float("nan")
                blocked = 0  # vehicles stopped on the blocked street, the accident excluded
                if incident:
                    edge = env.conn.edge
                    blocked = edge.getLastStepHaltingNumber(incident["edge"])
                    blocked -= "incident_0" in edge.getLastStepVehicleIDs(incident["edge"])
                aff = trips["aff"]
                peds = None
                if pedestrians:
                    person = env.conn.person
                    peds = sum(person.getSpeed(q) < 0.1 for q in person.getIDList())
                stats.put(
                    {
                        "side": 0 if x == 0 else 1,
                        "t": env.now,
                        "halting": halting,
                        "arrived": trips["arrived"],
                        "mean_tt": mean_tt,
                        "ev": dict(trips["ev"]),
                        "blocked": max(blocked, 0),
                        "aff": (len(aff), sum(aff) / len(aff) if aff else float("nan")),
                        "peds": peds,
                    }
                )
            if sync is not None and env.now % 60 < env.delta:  # both windows wait every minute
                with contextlib.suppress(Exception):  # the other window may have closed
                    sync.wait(timeout=300)
            if meet_at is not None and env.now >= meet_at:
                pace["on"] = True
                meet_at = None
            if gui and follow_ev:
                # while the camera follows a vehicle the window is not redrawn between TraCI
                # calls, so its zoom is set from the one measured at framing, not measured
                follow_zoom = framed["zoom"] * framed["width"] / ev_view_width
                if tracked is not None and tracked not in env.ev_ids:  # it has arrived
                    env.conn.gui.trackVehicle("View #0", "")
                    env.conn.gui.setZoom("View #0", framed["zoom"])
                    frame_view(env, episode.net_file, view_width)
                    tracked = None
                    on_incident = False
                # only a vehicle driving now (not one being teleported or just arrived)
                on_road = sorted(set(env.ev_ids) & set(env.conn.vehicle.getIDList()))
                if only_ev:  # that one only, once
                    on_road = [v for v in on_road if v == only_ev and rec["arrive"] is None]
                if tracked is None and on_road:
                    try:
                        env.conn.gui.trackVehicle("View #0", on_road[0])
                    except TraCIException:
                        pass  # it left the network in between; try again at the next decision
                    else:
                        tracked = on_road[0]
                        env.conn.gui.setZoom("View #0", follow_zoom)
                        rec["on"] = record
                        print(f"{method}: t={env.now:.0f} s, following emergency vehicle {tracked}")
            if only_ev and rec["arrive"] is not None and env.now >= rec["arrive"] + 8:
                trip = rec["arrive"] - (rec["depart"] or rec["arrive"])
                print(f"{method}: {only_ev} departed at t={rec['depart']:.0f} s, arrived at "
                      f"t={rec['arrive']:.0f} s: {trip:.0f} s on the road")  # fmt: skip
                if record:
                    meta = {"method": method, "label": label(method), "ev": only_ev,
                            "depart": rec["depart"], "arrive": rec["arrive"], "seed": seed,
                            "network": network, "demand": demand}  # fmt: skip
                    (rec["dir"] / f"{rec['side']}.json").write_text(json.dumps(meta))
                if sync is not None:
                    sync.abort()  # the other window goes on alone until its own arrival
                break
            if gui and incident:
                # the stopped vehicle is in the network from its insertion (at the accident's
                # start, later if its lane is full) until it drives off at the end
                here = env.now >= incident["start"] and "incident_0" in env.conn.vehicle.getIDList()
                if here and not accident["shown"]:
                    accident["shown"] = show_accident(env, sign)
                    if accident["shown"]:
                        print(
                            f"{method}: t={env.now:.0f} s, accident: one lane blocked until "
                            f"t={incident['end']:.0f} s (red zone)"
                        )
                elif accident["shown"] and not here:
                    hide_accident(env)
                    accident["shown"] = False
                    print(f"{method}: t={env.now:.0f} s, the accident vehicle has left")
                    if on_incident:
                        frame_view(env, episode.net_file, view_width)
                        on_incident = False
                aim = follow_incident and accident["shown"] and not on_incident
                if aim and tracked is None and accident["tries"] < 3:
                    with contextlib.suppress(TraCIException):  # it may leave in between
                        pos = env.conn.vehicle.getPosition("incident_0")
                        width = zoom_to(env, INCIDENT_VIEW_WIDTH, pos)
                        accident["tries"] += 1
                        # a window not redrawn yet is measured wrong: retry at the next decision
                        if abs(width - INCIDENT_VIEW_WIDTH) < 0.2 * INCIDENT_VIEW_WIDTH:
                            on_incident = True
                            accident["tries"] = 0
                            print(f"{method}: the camera shows the blocked street")
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
    except FatalTraCIError:  # the window was closed, or sumo-gui stopped (e.g. its 3D view)
        print(f"{method}: the SUMO window closed; the other window goes on alone")
        if sync is not None:
            sync.abort()  # never leave the other window waiting for this one
        return
    env.close()
    print(f"{method}: finished at t={env.now:.0f} s, {env.teleports} teleports")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", default="ft")
    parser.add_argument("--right", default="coop_full")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="policy of the learned controller (default: its training run 1 on the network)",
    )
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help="default: emergency buses, plus pedestrians where the network has sidewalks",
    )
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--delay", type=int, default=40, help="ms per simulation step")
    parser.add_argument(
        "--view-width", type=float, default=300.0, help="metres shown across the window"
    )
    parser.add_argument(
        "--follow-ev", action="store_true", help="the camera follows each emergency vehicle"
    )
    parser.add_argument(
        "--follow-incident",
        action="store_true",
        help="add the accident scenario and show the blocked street",
    )
    parser.add_argument(
        "--only-ev", default=None, help="follow this emergency vehicle only (e.g. ev_1)"
    )
    parser.add_argument(
        "--record", action="store_true", help="screenshots while following it (demo_record.py)"
    )
    parser.add_argument(
        "--ev-view-width", type=float, default=EV_VIEW_WIDTH,
        help="metres shown while the camera follows an emergency vehicle",
    )  # fmt: skip
    parser.add_argument("--no-chart", action="store_true", help="no live comparison chart")
    parser.add_argument("--headless", action="store_true", help="no window (checks the setup)")
    parser.add_argument("--quick", action="store_true", help="short episode")
    parser.add_argument(
        "--snapshot-at", type=float, nargs="*", default=[], help="simulation times (s)"
    )
    parser.add_argument(
        "--stop-after-snapshots", action="store_true", help="close once the screenshots exist"
    )
    args = parser.parse_args()
    from cotraffic.envs.episodes import unsupported

    excluded = unsupported(args.net)
    if args.scenarios is None:
        args.scenarios = ["emergency", "buses"]
        if "pedestrians" not in excluded:
            args.scenarios.append("pedestrians")
    if excluded & set(args.scenarios):
        parser.error(
            f"{args.net} cannot run {', '.join(sorted(excluded & set(args.scenarios)))}: its "
            "OpenStreetMap import has almost no sidewalks (FAILURES F-011); "
            "pedestrians are on the grids, e.g. --net grid4x4"
        )
    if args.follow_incident and "incident" not in args.scenarios:
        args.scenarios = [*args.scenarios, "incident"]
    if args.only_ev or args.record:
        args.follow_ev = True
    if args.record and not args.only_ev:
        parser.error("--record needs --only-ev (the vehicle the recording follows)")
    sync = None if args.headless else mp.Barrier(2)
    stats = None if args.headless or args.no_chart else mp.Queue()
    jobs = []
    for method, x in ((args.left, 0), (args.right, 960)):
        agent = "coop_full" if method == CANDIDATE else method  # built on COOP-FULL
        ckpt = (
            None if method in BASELINES else args.checkpoint or default_checkpoint(agent, args.net)
        )
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
                sync,
                stats,
                args.follow_incident,
                args.only_ev,
                args.record,
                args.ev_view_width,
            ),
        )
        p.start()
        jobs.append(p)
    if stats is not None:
        from cotraffic import config

        ev = config.load_protocol()["quick" if args.quick else "evaluation"]
        start = float(ev["warmup_s"])
        measured = (start, start + float(ev["measure_s"]))
        incident = None
        if "incident" in args.scenarios:  # same timing as the demand generator
            inc = config.load("scenarios", "incident")["incident"]
            scale = float(ev["measure_s"]) / 3600
            begin = start + float(inc["start_s"]) * scale
            incident = (begin, begin + float(inc["duration_s"]) * scale)
        from demo_chart import live_chart

        live_chart(
            stats,
            jobs,
            (args.left, args.right),
            measured,
            args.net,
            incident,
            end_s=measured[1] + float(ev["cooldown_s"]),
            pedestrians="pedestrians" in args.scenarios,
            emergency="emergency" in args.scenarios,
        )
    for p in jobs:
        p.join()


if __name__ == "__main__":
    main()
