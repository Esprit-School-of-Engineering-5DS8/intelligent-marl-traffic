"""Report figures, generated from result files only (``python -m cotraffic figures``).

Every figure is saved as PNG and SVG in ``figures/``. A figure whose data does not exist
yet is skipped with a message, never drawn from placeholder numbers. The tables of
``REPORT_TABLES.md`` give the exact values behind each figure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cotraffic import config  # noqa: E402
from cotraffic.analysis.aggregate import load_raw, summarise  # noqa: E402
from cotraffic.analysis.style import (  # noqa: E402
    BASELINE_METHODS,
    DEMAND_ORDER,
    GRID,
    METHOD_COLORS,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    label,
    method_sort_key,
)
from cotraffic.paths import FIGURES_DIR, LOGS_DIR, RAW_DIR, SUMMARY_DIR, TRAINING_DIR  # noqa: E402

LEARNED = ("ind", "coop", "coop_eco05", "coop_eco", "coop_full")


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT_SECONDARY,
            "axes.titlecolor": TEXT_PRIMARY,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "axes.axisbelow": True,
            "xtick.color": TEXT_SECONDARY,
            "ytick.color": TEXT_SECONDARY,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "text.color": TEXT_PRIMARY,
            "lines.linewidth": 2,
            "lines.solid_capstyle": "round",
            "font.family": "DejaVu Sans",
        }
    )


_OUT = {"dir": FIGURES_DIR}


def _save(fig, name: str) -> Path:
    out_dir = _OUT["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{name}.png"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(out_dir / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)
    return png


def _methods(values: Sequence[str]) -> list[str]:
    return sorted(set(values), key=method_sort_key)


def _bars(
    ax,
    groups: list[str],
    methods: list[str],
    getter: Callable[[str, str], tuple | None],
    group_labels: dict[str, str] | None = None,
) -> None:
    """Grouped bars with 95% CI whiskers; getter(group, method) -> (mean, lo, hi) or None."""
    n = max(1, len(methods))
    width = min(0.8 / n, 0.18)
    for i, method in enumerate(methods):
        xs, means, errs = [], [], [[], []]
        for g, group in enumerate(groups):
            value = getter(group, method)
            if value is None:
                continue
            mean, lo, hi = value
            xs.append(g + (i - (n - 1) / 2) * (width + 0.01))
            means.append(mean)
            errs[0].append(max(0.0, mean - lo))
            errs[1].append(max(0.0, hi - mean))
        if xs:
            ax.bar(
                xs,
                means,
                width=width,
                color=METHOD_COLORS.get(method, TEXT_SECONDARY),
                label=label(method),
                edgecolor=SURFACE,
                linewidth=1,
            )
            ax.errorbar(
                xs, means, yerr=errs, fmt="none", ecolor=TEXT_SECONDARY, elinewidth=1, capsize=2
            )
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([(group_labels or {}).get(g, g) for g in groups])
    ax.grid(axis="x", visible=False)


NETWORK_ORDER = ("grid4x4", "real_district", "grid8x8")


def _networks(df: pd.DataFrame, exclude: tuple[str, ...] = ("grid8x8",)) -> list[str]:
    """Networks present in ``df``, in the report's order."""
    if df.empty:
        return []
    present = [n for n in df["network"].unique() if n not in exclude]
    return sorted(present, key=lambda n: (NETWORK_ORDER.index(n) if n in NETWORK_ORDER else 9, n))


class Data:
    """Lazy access to result files."""

    def __init__(
        self, raw_dir: Path = RAW_DIR, logs_dir: Path = LOGS_DIR, allow_quick: bool = False
    ):
        self.raw = (
            load_raw(raw_dir, allow_quick) if any(Path(raw_dir).glob("*.csv")) else pd.DataFrame()
        )
        self.summary = summarise(self.raw) if not self.raw.empty else pd.DataFrame()
        self.logs_dir = logs_dir

    def ci(self, metric: str, **where) -> tuple[float, float, float] | None:
        s = self.summary
        if s.empty:
            return None
        sel = s["metric"] == metric
        for key, value in where.items():
            sel &= s[key] == value
        rows = s[sel]
        if rows.empty:
            return None
        r = rows.iloc[0]
        return float(r["mean"]), float(r["ci_lo"]), float(r["ci_hi"])

    def cell(self, **where) -> pd.DataFrame:
        df = self.raw
        if df.empty:
            return df
        sel = np.ones(len(df), dtype=bool)
        for key, value in where.items():
            sel &= (df[key] == value).to_numpy()
        return df[sel]

    def series(self, run_ids: Sequence[str], kind: str = "timeseries") -> pd.DataFrame:
        frames = [
            pd.read_csv(p)
            for rid in run_ids
            if (p := self.logs_dir / kind / f"{rid}.csv").is_file()
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------- figures
def fig01_training_curves(d: Data) -> Path | None:
    """One panel per demand level: training episodes draw a random level, so a single
    curve would mostly show which levels happened to be drawn."""
    net = "grid4x4"
    runs = {}
    for agent in LEARNED:
        logs = [
            pd.read_csv(p) for p in sorted((TRAINING_DIR / agent / net).glob("seed*/episodes.csv"))
        ]
        logs = [ep for ep in logs if len(ep) >= 4]
        if logs:
            runs[agent] = logs
    if not runs:
        return None
    levels = [
        lv
        for lv in DEMAND_ORDER
        if any((ep["episode_demand"] == lv).any() for logs in runs.values() for ep in logs)
    ]
    fig, axes = plt.subplots(1, len(levels), figsize=(3.2 * len(levels), 3.2), squeeze=False)
    for ax, level in zip(axes[0], levels, strict=True):
        for agent, logs in runs.items():
            curves = []
            for ep in logs:
                sub = ep[ep["episode_demand"] == level]
                if len(sub) >= 2:
                    curves.append(
                        (
                            sub["timesteps"].to_numpy(),
                            sub["mean_halting"].rolling(3, min_periods=1).mean().to_numpy(),
                        )
                    )
            if not curves:
                continue
            lo = max(c[0].min() for c in curves)
            hi = min(c[0].max() for c in curves)
            grid = np.linspace(lo, hi, 40) if hi > lo else np.array([lo])
            ys = np.array([np.interp(grid, x, y) for x, y in curves])
            seeds = "seed" if len(curves) == 1 else "seeds"
            color = METHOD_COLORS[agent]
            ax.plot(
                grid / 1000,
                ys.mean(0),
                color=color,
                label=f"{label(agent)} ({len(curves)} {seeds})",
            )
            if len(curves) > 1:
                ax.fill_between(
                    grid / 1000,
                    ys.mean(0) - ys.std(0),
                    ys.mean(0) + ys.std(0),
                    color=color,
                    alpha=0.12,
                    linewidth=0,
                )
        ax.set_title(level)
        ax.set_xlabel("Training steps (thousands)")
    axes[0, 0].set_ylabel("Halting vehicles at the signals")
    axes[0, 0].legend()
    fig.suptitle(
        "Training on grid4x4 - episodes of each demand level (rolling mean of 3), "
        "mean ± std over seeds",
        fontsize=9,
        color=TEXT_SECONDARY,
    )
    fig.tight_layout()
    return _save(fig, "fig01_training_curves")


def fig02_travel_time(d: Data) -> Path | None:
    nets = _networks(d.cell(scenario="normal"))
    if not nets:
        return None
    fig, axes = plt.subplots(len(nets), 1, figsize=(8.5, 3.3 * len(nets)), squeeze=False)
    for ax, net in zip(axes[:, 0], nets, strict=True):
        cell = d.cell(network=net, scenario="normal")
        demands = [x for x in DEMAND_ORDER if x in set(cell["demand"])]
        methods = _methods(cell["method"])
        _bars(
            ax,
            demands,
            methods,
            lambda g, m, net=net: d.ci(
                "mean_travel_time", network=net, scenario="normal", demand=g, method=m
            ),
        )
        ax.set_ylabel("Mean travel time (s)")
        ax.set_title(f"{net} - normal scenario (mean and 95% CI over runs)")
        ax.legend(ncol=min(len(methods), 5), loc="upper left")
    fig.tight_layout()
    return _save(fig, "fig02_travel_time_by_demand")


def fig03_improvement_heatmap(d: Data) -> Path | None:
    cell = d.cell(network="grid4x4")
    if cell.empty or "ft" not in set(cell["method"]):
        return None
    means = (
        cell.groupby(["scenario", "demand", "method"])["mean_travel_time"].mean().unstack("method")
    )
    if "ft" not in means:
        return None
    improvement = (means.rsub(means["ft"], axis=0)).div(means["ft"], axis=0) * 100
    improvement = improvement.drop(columns="ft")
    if (
        improvement.empty
        or improvement.columns.empty
        or not np.isfinite(improvement.to_numpy()).any()
    ):
        return None
    cols = _methods(improvement.columns)
    improvement = improvement[cols]
    order = sorted(
        improvement.index,
        key=lambda k: (
            k[0] != "normal",
            k[0],
            DEMAND_ORDER.index(k[1]) if k[1] in DEMAND_ORDER else 9,
        ),
    )
    improvement = improvement.loc[order]
    fig, ax = plt.subplots(figsize=(1.1 * len(cols) + 2.5, 0.42 * len(order) + 1.4))
    limit = max(5.0, float(np.nanmax(np.abs(improvement.to_numpy()))))
    im = ax.imshow(improvement.to_numpy(), cmap="RdBu", vmin=-limit, vmax=limit, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([label(c) for c in cols], rotation=30, ha="right")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{s} / {dm}" for s, dm in order])
    ax.grid(False)
    for i in range(len(order)):
        for j in range(len(cols)):
            v = improvement.iloc[i, j]
            if np.isfinite(v):
                ink = SURFACE if abs(v) > 0.55 * limit else TEXT_PRIMARY
                ax.text(j, i, f"{v:+.0f}%", ha="center", va="center", fontsize=7, color=ink)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Travel time improvement vs FT (%) - blue = better")
    ax.set_title("grid4x4 - change in mean travel time against fixed-time control")
    fig.tight_layout()
    return _save(fig, "fig03_improvement_heatmap")


def fig04_pareto(d: Data) -> Path | None:
    panels = []
    for demand in ("medium", "peak"):
        cell = d.cell(network="grid4x4", scenario="normal", demand=demand)
        if not cell.empty and {"coop", "coop_eco"} & set(cell["method"]):
            panels.append(demand)
    if not panels:
        return None
    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 3.8), squeeze=False)
    for ax, demand in zip(axes[0], panels, strict=True):
        cell = d.cell(network="grid4x4", scenario="normal", demand=demand)
        for method in _methods(cell["method"]):
            x = d.ci(
                "co2_g_per_km", network="grid4x4", scenario="normal", demand=demand, method=method
            )
            y = d.ci(
                "mean_travel_time",
                network="grid4x4",
                scenario="normal",
                demand=demand,
                method=method,
            )
            if x is None or y is None:
                continue
            ax.errorbar(
                x[0],
                y[0],
                xerr=[[x[0] - x[1]], [x[2] - x[0]]],
                yerr=[[y[0] - y[1]], [y[2] - y[0]]],
                fmt="o",
                color=METHOD_COLORS[method],
                ms=8,
                mec=SURFACE,
                mew=2,
                ecolor=TEXT_SECONDARY,
                elinewidth=1,
                capsize=2,
                label=label(method),
            )
        front = [m for m in ("coop", "coop_eco05", "coop_eco") if m in set(cell["method"])]
        if len(front) > 1:
            pts = [
                (
                    d.ci(
                        "co2_g_per_km",
                        network="grid4x4",
                        scenario="normal",
                        demand=demand,
                        method=m,
                    )[0],
                    d.ci(
                        "mean_travel_time",
                        network="grid4x4",
                        scenario="normal",
                        demand=demand,
                        method=m,
                    )[0],
                )
                for m in front
            ]
            ax.plot(*zip(*pts, strict=True), color=TEXT_SECONDARY, linewidth=1, zorder=0)
        ax.set_xlabel("CO2 (g/km)")
        ax.set_ylabel("Mean travel time (s)")
        ax.set_title(f"Travel time vs CO2 - grid4x4, {demand}")
        ax.legend(fontsize=7)
    fig.tight_layout()
    return _save(fig, "fig04_pareto_travel_time_co2")


def fig05_emergency(d: Data) -> Path | None:
    cell = d.cell(scenario="emergency")
    if cell.empty or "ev_delay" not in cell:
        return None
    nets = _networks(cell)
    if not nets:
        return None
    fig, axes = plt.subplots(len(nets), 2, figsize=(10, 3.2 * len(nets)), squeeze=False)
    for row, net in enumerate(nets):
        sub = cell[cell["network"] == net]
        demands = [x for x in DEMAND_ORDER if x in set(sub["demand"])]
        methods = _methods(sub["method"])
        for ax, metric, title in (
            (axes[row, 0], "ev_delay", "Emergency vehicle delay (s)"),
            (axes[row, 1], "mean_travel_time", "Travel time of all vehicles (s)"),
        ):
            _bars(
                ax,
                demands,
                methods,
                lambda g, m, metric=metric, net=net: d.ci(
                    metric, network=net, scenario="emergency", demand=g, method=m
                ),
            )
            ax.set_ylabel(title)
            ax.set_title(f"{net} - emergency scenario")
        axes[row, 0].legend(ncol=2)
    fig.tight_layout()
    return _save(fig, "fig05_emergency_vehicles")


def _mean_series(d: Data, cell: pd.DataFrame, column: str) -> pd.Series | None:
    ts = d.series(cell["run_id"].tolist())
    if ts.empty:
        return None
    return ts.groupby("minute")[column].mean()


def fig06_incident(d: Data) -> Path | None:
    cell = d.cell(network="grid4x4", scenario="incident", demand="peak")
    if cell.empty:
        return None
    fig, (local, network) = plt.subplots(2, 1, figsize=(8, 5.4), sharex=True)
    for method in _methods(cell["method"]):
        runs = cell[cell["method"] == method]
        ts = d.series(runs["run_id"].tolist())
        if ts.empty:
            continue
        mean = ts.groupby("minute").mean(numeric_only=True)
        color = METHOD_COLORS[method]
        if "incident_edge_halting" in mean:
            local.plot(mean.index, mean["incident_edge_halting"], color=color, label=label(method))
        network.plot(mean.index, mean["halting"], color=color, label=label(method))
    start = pd.to_numeric(cell["incident_start"], errors="coerce").dropna()
    if not start.empty:
        scen = config.load("scenarios", "incident")["incident"]
        begin = float(start.median()) / 60
        for ax in (local, network):
            ax.axvspan(
                begin, begin + float(scen["duration_s"]) / 60, color=GRID, alpha=0.8, linewidth=0
            )
        local.text(
            begin + 0.5,
            0.92,
            "lane blocked",
            fontsize=8,
            color=TEXT_SECONDARY,
            va="top",
            transform=local.get_xaxis_transform(),
        )
    local.set_ylabel("Halting on the blocked approach")
    local.set_title("Incident on grid4x4 at peak demand - mean over runs")
    local.legend(ncol=3)
    network.set_xlabel("Simulation time (min)")
    network.set_ylabel("Halting in the network")
    fig.tight_layout()
    return _save(fig, "fig06_incident_queues")


def fig07_rush_profile(d: Data) -> Path | None:
    cell = d.cell(network="grid4x4", scenario="normal", demand="rush_profile")
    if cell.empty:
        return None
    protocol = config.load_protocol()
    warmup = float(protocol["evaluation"]["warmup_s"])
    profile = config.load("demand", "rush_profile")["profile"]
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(8, 4.8), sharex=True, gridspec_kw={"height_ratios": [1, 2.6]}
    )
    measure = float(protocol["evaluation"]["measure_s"])
    t = [0.0] + [warmup + p[0] for p in profile] + [warmup + measure, warmup + measure]
    level = [profile[0][1]] + [p[1] for p in profile] + [profile[-1][1], 0.0]
    top.plot(np.array(t) / 60, level, color=TEXT_SECONDARY)
    top.axvspan(0, warmup / 60, color=GRID, alpha=0.6, linewidth=0)
    top.text(
        0.5, 0.9, "warm-up", fontsize=7, color=TEXT_SECONDARY, transform=top.get_xaxis_transform()
    )
    top.set_ylabel("Demand\n(share of peak)")
    top.set_title("Rush-hour profile on grid4x4 - demand (top) and queues (bottom), mean over runs")
    for method in _methods(cell["method"]):
        s = _mean_series(d, cell[cell["method"] == method], "halting")
        if s is not None:
            bottom.plot(s.index, s.to_numpy(), color=METHOD_COLORS[method], label=label(method))
    bottom.set_xlabel("Simulation time (min)")
    bottom.set_ylabel("Halting vehicles")
    bottom.legend(ncol=3)
    fig.tight_layout()
    return _save(fig, "fig07_rush_profile")


def fig08_robustness(d: Data) -> Path | None:
    cell = d.cell(network="grid4x4", demand="peak")
    if cell.empty or not (
        cell["scenario"].str.startswith("comm_dropout").any()
        or (cell["scenario"] == "sensor_noise").any()
    ):
        return None
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    for method in ("ind", "coop", "coop_full", "mp"):
        pts = []
        for scenario, p in (
            ("normal", 0.0),
            ("comm_dropout_10", 0.1),
            ("comm_dropout_30", 0.3),
            ("comm_dropout_50", 0.5),
        ):
            ci = d.ci(
                "mean_travel_time",
                network="grid4x4",
                scenario=scenario,
                demand="peak",
                method=method,
            )
            if ci is not None and (method in ("coop", "coop_full") or scenario == "normal"):
                pts.append((p, *ci))
        if not pts:
            continue
        pts = np.array(pts)
        if len(pts) == 1:  # only evaluated without dropout: reference line
            uses_messages = (
                method != "mp" and config.load_agent(method)["observation"]["neighbours"]
            )
            a.axhline(
                pts[0, 1],
                color=METHOD_COLORS[method],
                linewidth=1.5,
                label=f"{label(method)} ({'no dropout' if uses_messages else 'no messages'})",
            )
        else:
            a.plot(
                pts[:, 0],
                pts[:, 1],
                "-o",
                color=METHOD_COLORS[method],
                ms=8,
                mec=SURFACE,
                mew=2,
                label=label(method),
            )
            a.fill_between(
                pts[:, 0],
                pts[:, 2],
                pts[:, 3],
                color=METHOD_COLORS[method],
                alpha=0.12,
                linewidth=0,
            )
    a.set_xlabel("Probability that a neighbour message is lost")
    a.set_ylabel("Mean travel time (s)")
    a.set_title("Communication dropout - grid4x4, peak")
    a.legend()
    methods = _methods(cell[cell["scenario"] == "sensor_noise"]["method"])
    if methods:
        _bars(
            b,
            ["normal", "sensor_noise"],
            methods,
            lambda g, m: d.ci(
                "mean_travel_time", network="grid4x4", scenario=g, demand="peak", method=m
            ),
            {"normal": "exact sensors", "sensor_noise": "noise + 20% dead detectors"},
        )
        b.set_ylabel("Mean travel time (s)")
        b.set_title("Sensor faults - grid4x4, peak")
        b.legend()
    else:
        b.set_visible(False)
    fig.tight_layout()
    return _save(fig, "fig08_robustness")


def fig09_scalability(d: Data) -> Path | None:
    cell = d.cell(network="grid8x8")
    if cell.empty:
        return None
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    demands = [x for x in DEMAND_ORDER if x in set(cell["demand"])]
    methods = _methods(cell["method"])
    _bars(
        a,
        demands,
        methods,
        lambda g, m: d.ci(
            "mean_travel_time", network="grid8x8", scenario="normal", demand=g, method=m
        ),
    )
    a.set_ylabel("Mean travel time (s)")
    a.set_title("grid8x8 (64 signals), policies trained on grid4x4")
    a.legend(ncol=2)
    learned = [m for m in methods if m not in BASELINE_METHODS]
    nets = ["grid4x4", "grid8x8"]
    _bars(
        b,
        nets,
        learned,
        lambda g, m: d.ci(
            "inference_ms_per_step", network=g, scenario="normal", demand=demands[-1], method=m
        ),
    )
    b.set_ylabel("Decision time for all signals (ms)")
    b.set_title("Controller computation per 5 s decision")
    b.legend()
    fig.tight_layout()
    return _save(fig, "fig09_scalability")


def fig10_equity(d: Data) -> Path | None:
    cell = d.cell(network="grid4x4", scenario="normal", demand="peak")
    if cell.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    drawn = False
    for method in _methods(cell["method"]):
        runs = cell[cell["method"] == method]
        dist = d.series(runs["run_id"].tolist(), "waiting_distributions")
        if dist.empty:
            continue
        counts = dist.groupby("wait_to_s")["vehicles"].sum()
        share = counts.cumsum() / counts.sum()
        gini = runs["gini_waiting_time"].mean()
        x = np.minimum(counts.index.to_numpy(dtype=float), 1e4)
        ax.step(
            x,
            share.to_numpy(),
            where="post",
            color=METHOD_COLORS[method],
            label=f"{label(method)} (Gini {gini:.2f})",
        )
        drawn = True
    if not drawn:
        plt.close(fig)
        return None
    ax.set_xlim(0, 600)
    ax.set_xlabel("Waiting time of a vehicle (s)")
    ax.set_ylabel("Share of vehicles waiting at most this long")
    ax.set_title("Who waits? Distribution of waiting times - grid4x4, peak (all runs pooled)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    return _save(fig, "fig10_equity_waiting_distribution")


def fig11_people(d: Data) -> Path | None:
    peds = d.cell(scenario="pedestrians")
    buses = d.cell(scenario="buses")
    if peds.empty and buses.empty:
        return None
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    for ax, cell, scenario, metric, title in (
        (a, peds, "pedestrians", "ped_mean_waiting_time", "Pedestrian mean waiting (s)"),
        (b, buses, "buses", "person_weighted_delay", "Person-weighted delay (s)"),
    ):
        if cell.empty or metric not in cell:
            ax.set_visible(False)
            continue
        cell = cell[cell["network"] == "grid4x4"]
        demands = [x for x in DEMAND_ORDER if x in set(cell["demand"])]
        _bars(
            ax,
            demands,
            _methods(cell["method"]),
            lambda g, m, metric=metric, scenario=scenario: d.ci(
                metric, network="grid4x4", scenario=scenario, demand=g, method=m
            ),
        )
        ax.set_ylabel(title)
        ax.set_title(f"grid4x4 - {scenario} scenario")
        ax.legend(ncol=2)
    fig.tight_layout()
    return _save(fig, "fig11_pedestrians_and_buses")


def fig12_importance(d: Data) -> Path | None:
    """Decisions changed when a block is shuffled, counted on the decisions where the block
    is non-zero (a sparse block such as emergency vehicles would otherwise look unused),
    with the effect of shuffling it online on travel time and emergency-vehicle delay."""
    files = sorted(SUMMARY_DIR.glob("importance_*.csv"))
    if not files:
        return None
    frames = [pd.read_csv(f) for f in files]
    fig, axes = plt.subplots(1, len(frames), figsize=(6.2 * len(frames), 3.4), squeeze=False)
    for ax, df in zip(axes[0], frames, strict=True):
        rate = (
            "action_change_rate_active"
            if "action_change_rate_active" in df
            else ("action_change_rate")
        )
        df = df.sort_values(rate)
        method = df["method"].iloc[0]
        values = df[rate].to_numpy() * 100
        ax.barh(df["group"], values, color=METHOD_COLORS.get(method, TEXT_SECONDARY), height=0.5)
        for y, (_, r) in enumerate(df.iterrows()):
            text = f"travel time {r['travel_time_increase_pct']:+.1f}%"
            if not np.isnan(r.get("ev_delay_increase_pct", np.nan)) and (
                r["group"] == "emergency vehicles"
            ):
                text += f"\nEV delay {r['ev_delay_increase_pct']:+.0f}%"
            share = 100 * r.get("active_share", 1.0)
            if share < 95:
                text += f"\nnon-zero in {share:.1f}% of decisions"
            ax.text(values[y] + 0.5, y, text, va="center", fontsize=7, color=TEXT_SECONDARY)
        ax.set_xlabel(
            "Decisions changed when shuffled (%)\namong decisions where the block is non-zero"
        )
        ax.set_title(
            f"What {label(method)} relies on ({df['network'].iloc[0]}, {df['scenario'].iloc[0]})"
        )
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, max(10.0, float(values.max()) * 2.0))
    fig.tight_layout()
    return _save(fig, "fig12_feature_importance")


FIGURES = [
    fig01_training_curves,
    fig02_travel_time,
    fig03_improvement_heatmap,
    fig04_pareto,
    fig05_emergency,
    fig06_incident,
    fig07_rush_profile,
    fig08_robustness,
    fig09_scalability,
    fig10_equity,
    fig11_people,
    fig12_importance,
]


def build_figures(
    raw_dir: Path = RAW_DIR,
    logs_dir: Path = LOGS_DIR,
    out_dir: Path = FIGURES_DIR,
    allow_quick: bool = False,
) -> list[str]:
    _style()
    _OUT["dir"] = out_dir
    d = Data(raw_dir, logs_dir, allow_quick)
    report = []
    for fn in FIGURES:
        out = fn(d)
        report.append(f"{fn.__name__}: {out if out else 'skipped (no data yet)'}")
    return report
