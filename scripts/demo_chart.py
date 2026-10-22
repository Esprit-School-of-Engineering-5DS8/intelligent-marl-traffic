"""Live comparison chart of the side-by-side demo (third window, matplotlib).

Both controllers run the same traffic. Each one sends a record per decision (every 5 s):
``side`` (0 left, 1 right), ``t`` (s), ``halting`` (vehicles stopped at the signals),
``arrived``, ``mean_tt`` (mean trip time of the completed trips), ``ev`` (trip time of each
emergency vehicle that has arrived), ``blocked`` (vehicles stopped on the street of the
accident), ``aff`` (trips through that street: count, mean trip time) and ``peds``
(pedestrians standing still, ``None`` without pedestrians).

Colours mark the windows: left blue, right orange, a pair that stays distinct for
colour-blind viewers. The report's method colours are not distinct in every pair (MP
orange, COOP-FULL yellow), so the demo does not use them.
"""

from __future__ import annotations

import contextlib
import math
import queue
import time
from pathlib import Path

SIDE_COLORS = ("#2a78d6", "#eb6834")
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
CARD_EDGE = "#e7e5df"
MEASURED_BAND = "#f0efec"
ACCIDENT_BAND = "#f8dcdb"
BETTER = "#006300"
WORSE = "#d03b3b"
STEP_S = 5.0  # one record per decision
SMOOTH = 12  # records in a 1-minute average


def rolling(v: list[float], n: int = SMOOTH) -> list[float]:
    out, acc = [], 0.0
    for i, x in enumerate(v):
        acc += x - (v[i - n] if i >= n else 0.0)
        out.append(acc / min(i + 1, n))
    return out


def accumulated(v: list[float], per: float) -> list[float]:
    """Sum of count x 5 s, in units of ``per`` seconds (3600: hours, 60: minutes)."""
    out, acc = [], 0.0
    for x in v:
        acc += x * STEP_S / per
        out.append(acc)
    return out


def compare(left: float, right: float, names: list[str]) -> tuple[str, str]:
    """The right controller against the left one, for a measure where lower is better."""
    if not (math.isfinite(left) and math.isfinite(right)) or left <= 0:
        return "", MUTED
    pct = 100.0 * (right - left) / left
    if abs(pct) < 1.0:  # within the noise of a single episode
        return f"{names[1]}: about the same as {names[0]}", MUTED
    arrow, word, colour = ("▼", "lower", BETTER) if pct < 0 else ("▲", "higher", WORSE)
    return f"{arrow} {names[1]}: {abs(pct):.1f}% {word} than {names[0]}", colour


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
            f"  waiting at all signals: {sum(d['h'][i] for i in idx) * STEP_S / 3600:.1f} veh-h",
            "",
        ]
    return "\n".join(lines + [f"queues: minutes {t0:.0f}-{t1:.0f} (the accident + 10 min)"])


class Tile:
    """A headline number for both controllers, with the difference between them."""

    def __init__(self, ax, label: str, unit: str, names: list[str], fmt: str):
        from matplotlib.patches import FancyBboxPatch

        self.unit, self.names, self.fmt = unit, names, fmt
        ax.set_axis_off()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.add_patch(
            FancyBboxPatch(
                (0.0, 0.0),
                1.0,
                1.0,
                boxstyle="round,pad=0,rounding_size=0.06",
                facecolor="white",
                edgecolor=CARD_EDGE,
                linewidth=1.0,
                transform=ax.transAxes,
                clip_on=False,
            )
        )
        ax.text(0.06, 0.84, label, fontsize=10.5, color=INK_2, va="center")
        self.values = []
        for k, (name, colour) in enumerate(zip(names, SIDE_COLORS, strict=True)):
            y = 0.58 - 0.25 * k
            ax.plot([0.06, 0.13], [y, y], color=colour, lw=4, solid_capstyle="round")
            ax.text(0.17, y, name, fontsize=10, color=INK_2, va="center")
            self.values.append(
                ax.text(
                    0.94,
                    y,
                    "-",
                    fontsize=15,
                    fontweight="semibold",
                    color=INK,
                    ha="right",
                    va="center",
                )
            )
        self.delta = ax.text(0.06, 0.1, "", fontsize=9.5, va="center", color=MUTED)

    def update(self, left: float, right: float, note: str = "") -> None:
        for text, v in zip(self.values, (left, right), strict=True):
            text.set_text(f"{v:{self.fmt}} {self.unit}".strip() if math.isfinite(v) else "-")
        words, colour = compare(left, right, self.names)
        self.delta.set_text(words or note)
        self.delta.set_color(colour)


def live_chart(
    stats,
    jobs,
    methods,
    measured,
    network,
    incident=None,
    end_s=None,
    pedestrians=False,
    emergency=False,
) -> None:
    """Third window: the two controllers on the same traffic, updated as they run.

    ``measured``: the hour measured by the evaluation and ``incident``: the accident (start,
    end, simulation seconds), both shaded; ``end_s``: the end of the episode (fixed time axis).
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator

    from cotraffic.analysis.style import label

    names = [label(m) for m in methods]
    plt.rcParams.update(
        {
            "font.family": ["Segoe UI", "DejaVu Sans"],
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK_2,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
        }
    )

    panels = [
        ("stopped", "Vehicles stopped at the signals", "vehicles, 1-minute average"),
        ("waiting", "Waiting at the signals, accumulated", "vehicle-hours"),
        ("trip", "Mean trip time of completed trips", "seconds"),
    ]
    if pedestrians:
        panels.append(("peds", "Pedestrians waiting", "people standing still, 1-minute average"))
    if incident:
        panels.append(("blocked", "Queue on the blocked street", "vehicles, 1-minute average"))
    if emergency:
        panels.append(("ev", "Ambulances: trip time", "seconds, one bar per ambulance"))
    cols = 3 if len(panels) > 4 else 2
    rows = math.ceil(len(panels) / cols)

    fig = plt.figure(figsize=(16, 4.2 + 3.0 * rows), facecolor=SURFACE)
    with contextlib.suppress(AttributeError):  # no window when the figure is only saved
        fig.canvas.manager.set_window_title(f"{names[0]} vs {names[1]} - live comparison")
    grid = fig.add_gridspec(
        1 + rows,
        cols,
        height_ratios=[0.9] + [2.6] * rows,
        left=0.05,
        right=0.985,
        top=0.86,
        bottom=0.08,
        hspace=0.5,
        wspace=0.2,
    )
    fig.text(
        0.05,
        0.955,
        f"{names[0]} vs {names[1]}",
        fontsize=17,
        fontweight="semibold",
        color=INK,
        va="center",
    )
    fig.text(
        0.05,
        0.918,
        f"{network}, the same traffic in both windows",
        fontsize=11,
        color=INK_2,
        va="center",
    )
    fig.legend(
        handles=[Line2D([], [], color=c, lw=3) for c in SIDE_COLORS],
        labels=[f"left window: {names[0]}", f"right window: {names[1]}"],
        loc="center right",
        bbox_to_anchor=(0.985, 0.94),
        ncols=2,
        frameon=False,
        fontsize=11,
        handlelength=2.2,
    )
    clock = fig.text(0.985, 0.898, "", fontsize=10, color=MUTED, ha="right", va="center")
    note = "Grey band: the hour measured in the evaluation."
    if incident:
        note += " Red band: the accident (one lane blocked)."
    fig.text(0.05, 0.025, note, fontsize=9.5, color=MUTED)

    # headline numbers
    tile_specs = [
        ("trip", "Mean trip time", "s", ".0f"),
        ("waiting", "Waiting at the signals", "veh-h", ".1f"),
    ]
    if pedestrians:
        tile_specs.append(("peds", "Pedestrian waiting (person-min)", "", ".0f"))
    if emergency:
        tile_specs.append(("ev", "Ambulances, mean trip time", "s", ".0f"))
    if incident:
        tile_specs.append(("aff", "Trips through the blocked street", "s", ".0f"))
    tile_row = grid[0, :].subgridspec(1, len(tile_specs), wspace=0.08)
    tiles = {
        key: Tile(fig.add_subplot(tile_row[0, i]), title, unit, names, fmt)
        for i, (key, title, unit, fmt) in enumerate(tile_specs)
    }

    axes, lines, dots = {}, {}, {}
    for i, (key, title, unit) in enumerate(panels):
        ax = fig.add_subplot(grid[1 + i // cols, i % cols])
        axes[key] = ax
        ax.set_facecolor(SURFACE)
        ax.set_title(title, loc="left", fontsize=11.5, fontweight="semibold", color=INK, pad=16)
        ax.annotate(
            unit,
            xy=(0, 1),
            xycoords="axes fraction",
            xytext=(0, 5),
            textcoords="offset points",
            fontsize=9,
            color=MUTED,
        )
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(length=0)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        if key == "ev":
            continue
        ax.axvspan(measured[0] / 60, measured[1] / 60, color=MEASURED_BAND, zorder=0, lw=0)
        if incident:
            ax.axvspan(incident[0] / 60, incident[1] / 60, color=ACCIDENT_BAND, zorder=0, lw=0)
        if end_s:
            ax.set_xlim(0, end_s / 60 * 1.015)  # room for the end dots
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True, steps=[1, 2, 5, 10]))
        if i // cols == rows - 1 or i + cols >= len(panels):
            ax.set_xlabel("simulated time (min)", fontsize=9.5, color=MUTED)
        lines[key] = [
            ax.plot([], [], color=c, lw=2, solid_capstyle="round", solid_joinstyle="round")[0]
            for c in SIDE_COLORS
        ]
        dots[key] = [
            ax.plot([], [], "o", ms=8, mfc=c, mec=SURFACE, mew=2, zorder=5, clip_on=False)[0]
            for c in SIDE_COLORS
        ]
    for i in range(len(panels), rows * cols):  # an empty slot in the last row
        fig.add_subplot(grid[1 + i // cols, i % cols]).set_axis_off()

    plt.show(block=False)
    data = [
        {"t": [], "h": [], "a": [], "tt": [], "ev": {}, "b": [], "aff": (0, math.nan), "p": []}
        for _ in methods
    ]
    drawn_ev = None
    ev_artists: list = []

    def series(d) -> dict[str, list[float]]:
        out = {
            "stopped": rolling(d["h"]),
            "waiting": accumulated(d["h"], 3600),
            "trip": d["tt"],
        }
        if pedestrians:
            out["peds"] = rolling(d["p"])
        if incident:
            out["blocked"] = rolling(d["b"])
        return out

    def draw_ev() -> None:
        ax = axes["ev"]
        for artist in ev_artists:  # bars and their labels; the panel's unit line stays
            artist.remove()
        ev_artists.clear()
        ids = sorted(set(data[0]["ev"]) | set(data[1]["ev"]), key=lambda v: int(v[3:]))
        if not ids:
            note = ax.text(
                0.5,
                0.5,
                "no ambulance has arrived yet",
                ha="center",
                va="center",
                color=MUTED,
                fontsize=10,
                transform=ax.transAxes,
            )
            ev_artists.append(note)
            ax.set_xticks([])
            return
        top = max(max(d["ev"].values(), default=0.0) for d in data)
        for k in range(2):
            for i, v in enumerate(ids):
                if v not in data[k]["ev"]:
                    continue
                h = data[k]["ev"][v]
                x = i + (k - 0.5) * 0.36
                ev_artists.extend(ax.bar(x, h, width=0.32, color=SIDE_COLORS[k], zorder=3))
                label_text = ax.text(
                    x,
                    h + top * 0.02,
                    f"{h:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    color=INK_2,
                )
                ev_artists.append(label_text)
        ax.set_xticks(range(len(ids)), ids)
        ax.set_xlim(-0.6, len(ids) - 0.4)
        ax.set_ylim(0, top * 1.15)

    if emergency:
        draw_ev()
    while any(p.is_alive() for p in jobs) or not stats.empty():
        try:
            while True:
                r = stats.get_nowait()
                d = data[r["side"]]
                d["t"].append(r["t"] / 60)
                d["h"].append(r["halting"])
                d["a"].append(r["arrived"])
                d["tt"].append(r["mean_tt"])
                d["ev"] = r["ev"]
                d["b"].append(r["blocked"])
                d["aff"] = r["aff"]
                d["p"].append(r["peds"] or 0)
        except queue.Empty:
            pass
        if not plt.fignum_exists(fig.number):
            time.sleep(0.5)
            continue
        current = []
        for k, d in enumerate(data):
            values = series(d)
            for key, v in values.items():
                lines[key][k].set_data(d["t"], v)
                if d["t"]:
                    dots[key][k].set_data([d["t"][-1]], [v[-1]])
            current.append(values)
        # y axis from 0 to the highest value shown (set_ylim switches autoscaling off)
        for key, pair in lines.items():
            shown = [y for line in pair for y in line.get_ydata() if math.isfinite(y)]
            top = max(shown, default=0.0)
            axes[key].set_ylim(0, top * 1.12 if top > 0 else 1.0)
            if not end_s and shown:
                axes[key].set_xlim(0, max(d["t"][-1] for d in data if d["t"]))
        if emergency:
            ev_now = (len(data[0]["ev"]), len(data[1]["ev"]))
            if ev_now != drawn_ev:
                draw_ev()
                drawn_ev = ev_now
        if all(d["t"] for d in data):
            tiles["trip"].update(current[0]["trip"][-1], current[1]["trip"][-1])
            tiles["waiting"].update(current[0]["waiting"][-1], current[1]["waiting"][-1])
            if pedestrians:
                walked = [accumulated(d["p"], 60)[-1] for d in data]
                tiles["peds"].update(*walked)
            if emergency:
                both = sorted(set(data[0]["ev"]) & set(data[1]["ev"]))
                means = [
                    sum(d["ev"][v] for v in both) / len(both) if both else math.nan for d in data
                ]
                tiles["ev"].update(*means, note=f"{len(both)} arrived in both windows")
            if incident:
                tiles["aff"].update(
                    data[0]["aff"][1], data[1]["aff"][1], note="from 10 min before the accident"
                )
            clock.set_text(f"simulated time {min(d['t'][-1] for d in data):.0f} min")
        plt.pause(0.5)

    print()
    print("Same traffic, whole episode:")
    for name, d in zip(names, data, strict=True):
        if d["t"]:
            ev = ", ".join(f"{v}: {t:.0f} s" for v, t in sorted(d["ev"].items()))
            print(
                f"  {name:12s} {d['a'][-1]:6d} vehicles arrived, mean trip {d['tt'][-1]:5.0f} s, "
                f"{accumulated(d['h'], 3600)[-1]:6.1f} vehicle-hours waiting at the signals"
                + (
                    f", {accumulated(d['p'], 60)[-1]:.0f} person-minutes of pedestrian waiting"
                    if pedestrians
                    else ""
                )
                + (f"; emergency vehicles {ev}" if ev else "")
            )
    if incident and all(d["t"] for d in data):
        print("During the accident:")
        for line in incident_summary(data, names, incident).splitlines():
            print(f"  {line}")
    out_dir = Path(__file__).resolve().parents[1] / "results" / "tmp" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"compare_{network}_{methods[0]}_vs_{methods[1]}.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"chart saved: {out}")
    if plt.fignum_exists(fig.number):
        plt.show()  # stays open until closed
