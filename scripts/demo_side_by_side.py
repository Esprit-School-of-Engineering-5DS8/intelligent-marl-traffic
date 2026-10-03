"""Two sumo-gui windows side by side, same demand and events, two controllers.

Default: the real district at peak with emergency vehicles and buses, fixed-time signals (the
status quo) on the left and COOP-FULL on the right. Record the screen. For the strongest
classical controller use ``--left mp``, or ``--left ev_rule_mp`` for Max-Pressure with
emergency-vehicle preemption (report, section 8.2).

    python scripts/demo_side_by_side.py [--left ft] [--right coop_full]
        [--checkpoint results/checkpoints/coop_full/real_district/seed1.zip]
        [--net real_district] [--demand peak] [--scenarios emergency buses] [--seed 3]

Display only (the simulation is unchanged): vehicles and pedestrians are drawn as shapes
in one colour per type - cars blue-grey, buses amber, emergency vehicles (ambulances)
white with a green cross, the accident vehicle magenta, pedestrians cyan - with a legend naming the
controller in each window. The view opens 300 m wide around the signals (``--view-width``);
zoom and pan with the mouse. ``--follow-ev`` makes the camera follow each emergency
vehicle (ids ``ev_0``, ``ev_1``...) from departure to arrival, in both windows; the
simulation fast-forwards to 30 s before the first one departs. Both windows wait for each
other at that point (or after the first minute), then run in step.
``--follow-incident`` adds the accident scenario (a vehicle stopped on one lane just before
a junction for 15 min, magenta) and puts the camera on the blocked street, in both
windows; the simulation fast-forwards to 1 min before the accident.
``--snapshot-at 900 1800`` saves screenshots of both windows at those simulation times
(``results/tmp/demo/``), e.g. for the report.

A third window charts both controllers live on the same traffic (stopped vehicles, mean
trip time, arrivals), with the hour measured by the evaluation shaded (and the accident,
with a panel for the vehicles stopped on the blocked street); the chart is saved
at the end (``--no-chart`` to skip it). The two windows wait for each other every
simulated minute so that they show the same moment.

``--headless`` runs both controllers without windows (checks the setup).
"""

from __future__ import annotations

import argparse
import contextlib
import multiprocessing as mp
import time
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
INCIDENT_VIEW_WIDTH = 200.0  # metres shown around the accident vehicle
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
    <delay value="0"/>
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


def view_settings(title: str, tag: str) -> Path:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    legend = DEMO_DIR / f"legend_{tag}.png"
    w, h = draw_legend(title, legend)
    settings = DEMO_DIR / f"view_{tag}.xml"
    settings.write_text(
        SETTINGS.format(
            legend=legend.as_posix(),
            cx=w // 2 + 10,
            cy=h // 2 + 10,
            w=w,
            h=h,
        ),
        encoding="utf-8",
    )
    return settings


def ev_departures(episode) -> list[float]:
    """Departure times of the emergency vehicles (ids ev_0, ev_1, ...) of the episode."""
    import re

    times: list[float] = []
    for f in episode.bundle.route_files:
        text = Path(f).read_text(encoding="utf-8")
        times += [
            float(t) for t in re.findall(r'<vehicle id="ev_\d+"[^>]*depart="([0-9.]+)"', text)
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
    # pacing: sumo-gui runs without its own delay; we pause after each simulated second,
    # except while fast-forwarding (TraCI cannot change the delay of the window)
    pace = {"on": True}

    def pause(env, now: float) -> None:
        if pace["on"] and delay > 0:
            time.sleep(delay / 1000)

    if gui:
        hooks.append(pause)
    incident = episode.bundle.meta.get("incident")
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
        settings = view_settings(f"{side}: {label(method)}", f"{side}_{method}")
        options = ["--window-pos", f"{x},30", "--window-size", "940,900"]
        options += ["--gui-settings-file", str(settings)]
        options += ["--error-log", str(DEMO_DIR / f"sumo_{side}_{method}.log")]
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
    meet_at = None  # simulation time at which both windows wait for each other
    on_incident = False  # the camera shows the blocked street
    if gui:
        meet_at = reframe_until
        targets = []
        departures = ev_departures(episode) if follow_ev else []
        if follow_ev and not departures:
            print(f"{method}: no emergency vehicle in this scenario (add --scenarios emergency)")
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
                stats.put(
                    (
                        0 if x == 0 else 1,
                        env.now,
                        halting,
                        trips["arrived"],
                        mean_tt,
                        dict(trips["ev"]),
                        max(blocked, 0),
                        (len(aff), sum(aff) / len(aff) if aff else float("nan")),
                    )
                )
            if sync is not None and env.now % 60 < env.delta:  # both windows wait every minute
                with contextlib.suppress(Exception):  # the other window may have closed
                    sync.wait(timeout=300)
            if meet_at is not None and env.now >= meet_at:
                pace["on"] = True
                meet_at = None
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
                    on_incident = False
                # only a vehicle driving now (not one being teleported or just arrived)
                on_road = sorted(set(env.ev_ids) & set(env.conn.vehicle.getIDList()))
                if tracked is None and on_road:
                    try:
                        env.conn.gui.trackVehicle("View #0", on_road[0])
                    except TraCIException:
                        pass  # it left the network in between; try again at the next decision
                    else:
                        tracked = on_road[0]
                        zoom = env.conn.gui.getZoom("View #0") * factor
                        env.conn.gui.setZoom("View #0", zoom)
                        print(f"{method}: t={env.now:.0f} s, following emergency vehicle {tracked}")
            if gui and follow_incident and incident and tracked is None:
                active = incident["start"] <= env.now < incident["end"]
                # only once it is on the road: a vehicle loaded but not yet inserted (its
                # lane full) has an invalid position; try again at the next decision
                if active and not on_incident and "incident_0" in env.conn.vehicle.getIDList():
                    with contextlib.suppress(TraCIException):  # it may leave in between
                        zoom_to(
                            env, INCIDENT_VIEW_WIDTH, env.conn.vehicle.getPosition("incident_0")
                        )
                        on_incident = True
                        print(
                            f"{method}: t={env.now:.0f} s, accident: the camera shows the "
                            "blocked street (magenta vehicle)"
                        )
                elif on_incident and not active:
                    frame_view(env, episode.net_file, view_width)
                    on_incident = False
                    print(f"{method}: t={env.now:.0f} s, the accident vehicle has left")
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


def incident_summary(data, names, incident) -> str:
    """The accident, controller by controller.

    Trips through the blocked street: those departing from 10 min before the accident to its
    end, as in the evaluation (on a two-lane street most drivers pass the stopped vehicle on
    the other lane, so their trip time shows the effect better than the queue). Queues: from
    the accident to 10 min after it, since the queue it leaves takes a few minutes to clear.
    """
    t0, t1 = incident[0] / 60, incident[1] / 60 + 10
    lines = []
    for name, d in zip(names, data, strict=True):
        idx = [i for i, t in enumerate(d["t"]) if t0 <= t <= t1]
        if not idx:
            return "the accident has not started yet"
        blocked = [d["b"][i] for i in idx]
        n, mean = d["aff"]
        lines += [
            name,
            f"  trips through the blocked street: {n} done"
            + (f", mean trip {mean:.0f} s" if n else ""),
            f"  stopped on that street: {sum(blocked) / len(blocked):.1f} on average,"
            f" {max(blocked):.0f} at most",
            f"  waiting at all signals: {sum(d['h'][i] for i in idx) * 5 / 3600:.1f} veh-h",
            "",
        ]
    return "\n".join(lines + [f"queues: minutes {t0:.0f}-{t1:.0f} (the accident + 10 min)"])


def live_chart(stats, jobs, methods, measured, network, incident=None) -> None:
    """Third window: the two controllers on the same traffic, updated as they run.

    Instantaneous queues are noisy, so the stopped-vehicle curve is a 1-minute average and a
    second panel accumulates the waiting at the signals: a small, steady difference between
    the controllers shows there as two curves drifting apart. With an accident (``incident``
    = its start and end, simulation seconds) its period is shaded in red and a fifth panel
    shows the vehicles stopped on the blocked street.
    """
    import queue

    import matplotlib.pyplot as plt

    from cotraffic.analysis.style import METHOD_COLORS, label

    names = [label(m) for m in methods]
    colors = [METHOD_COLORS.get(m, "#52514e") for m in methods]
    rgb = [tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors]
    if sum((a - b) ** 2 for a, b in zip(*rgb, strict=True)) ** 0.5 < 120:
        colors[1] = "#2a78d6"  # two similar hues would be hard to tell apart
    plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold"})
    if incident:
        fig, axes = plt.subplots(2, 3, figsize=(17, 7.8))
        ax_q, ax_w, ax_b, ax_t, ax_ev, ax_s = axes.ravel()
        timed = (ax_q, ax_w, ax_b, ax_t)
    else:
        fig, axes = plt.subplots(2, 2, figsize=(13, 7.6))
        ax_q, ax_w, ax_t, ax_ev = axes.ravel()
        ax_b = ax_s = None
        timed = (ax_q, ax_w, ax_t)
    for ax in timed:
        ax.axvspan(measured[0] / 60, measured[1] / 60, color="0.94", zorder=0)
        if incident:
            ax.axvspan(incident[0] / 60, incident[1] / 60, color="#f4c7c3", alpha=0.6, zorder=0)
        ax.set_xlabel("simulated time (min)")
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    ax_q.set_title("Vehicles stopped at the signals (1-min average)")
    ax_w.set_title("Waiting accumulated at the signals (vehicle-hours)")
    ax_t.set_title("Mean trip time of completed trips (s)")
    ax_ev.set_title("Emergency vehicles: trip time (s)")
    ax_ev.spines[["top", "right"]].set_visible(False)
    raw, smooth, cum, trip, block = [], [], [], [], []
    for n, c in zip(names, colors, strict=True):
        raw.append(ax_q.plot([], [], color=c, lw=0.8, alpha=0.25)[0])
        smooth.append(ax_q.plot([], [], color=c, lw=2.4, label=n)[0])
        cum.append(ax_w.plot([], [], color=c, lw=2.4, label=n)[0])
        trip.append(ax_t.plot([], [], color=c, lw=2.4, label=n)[0])
        if ax_b is not None:
            block.append(ax_b.plot([], [], color=c, lw=2.4, label=n)[0])
    ax_q.legend(loc="upper left", frameon=False)
    if ax_b is not None:
        ax_b.set_title("Stopped on the blocked street (1-min average)")
        ax_b.set_ylabel("accident vehicle not counted", color="0.4")
        ax_s.set_axis_off()
        summary = ax_s.text(0.02, 0.95, "", va="top", fontsize=11, transform=ax_s.transAxes)
        ax_s.set_title("During the accident", loc="left")
    status = fig.text(0.5, 0.945, "", ha="center", fontsize=11)
    fig.suptitle(f"{names[0]} vs {names[1]} on {network}, same traffic", fontsize=14, y=0.99)
    note = "grey band: the period measured in the evaluation"
    if incident:
        note += "; red band: the accident (one lane blocked)"
    fig.text(0.5, 0.012, note, ha="center", color="0.4")
    fig.tight_layout(rect=(0, 0.03, 1, 0.935))
    plt.show(block=False)
    data = [
        {"t": [], "h": [], "a": [], "tt": [], "ev": {}, "b": [], "aff": (0, float("nan"))}
        for _ in methods
    ]
    drawn_ev = None

    def rolling(v, n=12):  # 12 decisions of 5 s = 1 minute
        out, acc = [], 0.0
        for i, x in enumerate(v):
            acc += x - (v[i - n] if i >= n else 0.0)
            out.append(acc / min(i + 1, n))
        return out

    def cumulative_hours(v):
        out, acc = [], 0.0
        for x in v:
            acc += x * 5 / 3600  # vehicles stopped during a 5-s decision
            out.append(acc)
        return out

    def draw_ev() -> None:
        ax_ev.clear()
        ax_ev.set_title("Emergency vehicles: trip time (s)")
        ax_ev.spines[["top", "right"]].set_visible(False)
        ids = sorted(set(data[0]["ev"]) | set(data[1]["ev"]), key=lambda v: int(v[3:]))
        if not ids:
            ax_ev.text(
                0.5,
                0.5,
                "no emergency vehicle has arrived yet",
                ha="center",
                va="center",
                color="0.45",
                transform=ax_ev.transAxes,
            )
            ax_ev.set_xticks([])
            ax_ev.set_yticks([])
            return
        for k in range(2):
            xs = [i + (k - 0.5) * 0.38 for i in range(len(ids))]
            ys = [data[k]["ev"].get(v, 0.0) for v in ids]
            bars = ax_ev.bar(xs, ys, width=0.36, color=colors[k], label=names[k])
            for b, v in zip(bars, ids, strict=True):
                if v in data[k]["ev"]:
                    ax_ev.text(
                        b.get_x() + b.get_width() / 2,
                        b.get_height(),
                        f"{b.get_height():.0f}",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                    )
        ax_ev.set_xticks(range(len(ids)), [v[3:] for v in ids])
        ax_ev.set_xlabel("emergency vehicle, in order of departure")
        ax_ev.set_ylim(0, ax_ev.get_ylim()[1] * 1.25)  # room for the legend
        ax_ev.legend(loc="upper right", ncols=2, frameon=False)
        ax_ev.grid(axis="y", alpha=0.3)

    draw_ev()
    while any(p.is_alive() for p in jobs) or not stats.empty():
        try:
            while True:
                k, now, halting, arrived, mean_tt, ev, blocked, aff = stats.get_nowait()
                d = data[k]
                d["b"].append(blocked)
                d["aff"] = aff
                d["t"].append(now / 60)
                d["h"].append(halting)
                d["a"].append(arrived)
                d["tt"].append(mean_tt)
                d["ev"] = ev
        except queue.Empty:
            pass
        if plt.fignum_exists(fig.number):
            for k in range(len(methods)):
                d = data[k]
                raw[k].set_data(d["t"], d["h"])
                smooth[k].set_data(d["t"], rolling(d["h"]))
                cum[k].set_data(d["t"], cumulative_hours(d["h"]))
                trip[k].set_data(d["t"], d["tt"])
                if block:
                    block[k].set_data(d["t"], rolling(d["b"]))
            for ax in timed:
                ax.relim()
                ax.autoscale_view()
            if incident and data[0]["t"] and data[1]["t"]:
                summary.set_text(incident_summary(data, names, incident))
            ev_now = (len(data[0]["ev"]), len(data[1]["ev"]))
            if ev_now != drawn_ev:
                draw_ev()
                drawn_ev = ev_now
            if data[0]["t"] and data[1]["t"]:
                w = [cumulative_hours(d["h"])[-1] for d in data]
                t = [d["tt"][-1] for d in data]
                parts = [
                    f"{n}: {tt:.0f} s mean trip, {wh:.1f} veh-h waiting"
                    for n, tt, wh in zip(names, t, w, strict=True)
                ]
                status.set_text("   |   ".join(parts))
            plt.pause(0.5)
        else:
            time.sleep(0.5)
    print()
    print("Same traffic, whole episode:")
    for name, d in zip(names, data, strict=True):
        if d["t"]:
            ev = ", ".join(f"{v}: {t:.0f} s" for v, t in sorted(d["ev"].items()))
            print(
                f"  {name:12s} {d['a'][-1]:6d} vehicles arrived, mean trip {d['tt'][-1]:5.0f} s, "
                f"{cumulative_hours(d['h'])[-1]:6.1f} vehicle-hours waiting at the signals"
                + (f"; emergency vehicles {ev}" if ev else "")
            )
    if incident and all(d["t"] for d in data):
        print("During the accident:")
        for line in incident_summary(data, names, incident).splitlines():
            print(f"  {line}")
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    out = DEMO_DIR / f"compare_{network}_{methods[0]}_vs_{methods[1]}.png"
    fig.savefig(out, dpi=150)
    print(f"chart saved: {out}")
    if plt.fignum_exists(fig.number):
        plt.show()  # stays open until closed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", default="ft")
    parser.add_argument("--right", default="coop_full")
    parser.add_argument(
        "--checkpoint", default="results/checkpoints/coop_full/real_district/seed1.zip"
    )
    parser.add_argument("--net", default="real_district")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--scenarios", nargs="*", default=["emergency", "buses"])
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
    if args.follow_incident and "incident" not in args.scenarios:
        args.scenarios = [*args.scenarios, "incident"]
    sync = None if args.headless else mp.Barrier(2)
    stats = None if args.headless or args.no_chart else mp.Queue()
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
                sync,
                stats,
                args.follow_incident,
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
        live_chart(stats, jobs, (args.left, args.right), measured, args.net, incident)
    for p in jobs:
        p.join()


if __name__ == "__main__":
    main()
