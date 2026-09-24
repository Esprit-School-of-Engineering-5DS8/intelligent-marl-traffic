"""CoTraffic results dashboard: ``streamlit run dashboard/app.py``.

Reads the files in results/ only, so it runs on any machine without SUMO.
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from cotraffic.analysis.aggregate import load_raw, summarise
from cotraffic.analysis.style import (
    DEMAND_ORDER,
    METHOD_COLORS,
    METRIC_LABELS,
    label,
    method_sort_key,
)
from cotraffic.paths import LOGS_DIR, RAW_DIR, TRAINING_DIR

st.set_page_config(page_title="CoTraffic results", layout="wide")


@st.cache_data
def results() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_raw(RAW_DIR)
    return raw, summarise(raw)


def color_scale(methods: list[str]) -> alt.Scale:
    labels = [label(m) for m in methods]
    return alt.Scale(domain=labels, range=[METHOD_COLORS.get(m, "#52514e") for m in methods])


def series(run_ids: list[str], kind: str) -> pd.DataFrame:
    frames = [pd.read_csv(p) for r in run_ids if (p := LOGS_DIR / kind / f"{r}.csv").is_file()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


st.title("CoTraffic - cooperative traffic signal control")
if not any(Path(RAW_DIR).glob("*.csv")):
    st.warning("No result file in results/raw yet. Run `python -m cotraffic evaluate` first.")
    st.stop()
raw, summary = results()

c1, c2, c3, c4 = st.columns(4)
network = c1.selectbox("Network", sorted(raw["network"].unique()))
scenarios = sorted(raw[raw["network"] == network]["scenario"].unique())
scenario = c2.selectbox(
    "Scenario", scenarios, index=scenarios.index("normal") if "normal" in scenarios else 0
)
available = raw[(raw["network"] == network) & (raw["scenario"] == scenario)]
demands = [d for d in DEMAND_ORDER if d in set(available["demand"])]
demand = c3.selectbox(
    "Demand", demands, index=len(demands) - 1 if "peak" not in demands else demands.index("peak")
)
all_methods = sorted(available["method"].unique(), key=method_sort_key)
methods = c4.multiselect("Methods", all_methods, default=all_methods, format_func=label)

cell = summary[
    (summary["network"] == network)
    & (summary["scenario"] == scenario)
    & (summary["demand"] == demand)
    & (summary["method"].isin(methods))
].copy()
cell["Method"] = cell["method"].map(label)

tab_overview, tab_time, tab_tradeoff, tab_training, tab_decisions = st.tabs(
    ["Overview", "Over time", "Travel time vs CO2", "Training", "Decisions"]
)

with tab_overview:
    metrics = [m for m in METRIC_LABELS if m in set(cell["metric"])]
    metric = st.selectbox("Metric", metrics, format_func=lambda m: METRIC_LABELS[m])
    data = cell[cell["metric"] == metric]
    base = alt.Chart(data).encode(x=alt.X("Method:N", sort=[label(m) for m in methods], title=None))
    bars = base.mark_bar(size=24, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        y=alt.Y("mean:Q", title=METRIC_LABELS[metric]),
        color=alt.Color("Method:N", scale=color_scale(methods), legend=None),
        tooltip=[
            "Method",
            alt.Tooltip("mean:Q", format=".1f"),
            alt.Tooltip("ci_lo:Q", format=".1f"),
            alt.Tooltip("ci_hi:Q", format=".1f"),
            "n",
        ],
    )
    whiskers = base.mark_rule(color="#52514e").encode(y="ci_lo:Q", y2="ci_hi:Q")
    st.altair_chart(bars + whiskers, width="stretch")
    st.caption("Bars: mean over runs; whiskers: 95% bootstrap confidence interval.")
    table = cell.pivot_table(index="Method", columns="metric", values="mean").rename(
        columns=METRIC_LABELS
    )
    st.dataframe(table.round(2), width="stretch")

with tab_time:
    runs = raw[
        (raw["network"] == network)
        & (raw["scenario"] == scenario)
        & (raw["demand"] == demand)
        & (raw["method"].isin(methods))
    ]
    ts = series(runs["run_id"].tolist(), "timeseries")
    if ts.empty:
        st.info("No time series for this selection.")
    else:
        ts = ts.merge(runs[["run_id", "method"]], on="run_id")
        column = st.radio("Quantity", ["halting", "running", "mean_waiting_time"], horizontal=True)
        mean = ts.groupby(["method", "minute"])[column].mean().reset_index()
        mean["Method"] = mean["method"].map(label)
        chart = (
            alt.Chart(mean)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("minute:Q", title="Simulation time (min)"),
                y=alt.Y(f"{column}:Q", title=column),
                color=alt.Color("Method:N", scale=color_scale(methods)),
                tooltip=["Method", "minute", alt.Tooltip(f"{column}:Q", format=".1f")],
            )
        )
        st.altair_chart(chart, width="stretch")

with tab_tradeoff:
    pts = (
        cell[cell["metric"].isin(["mean_travel_time", "co2_g_per_km"])]
        .pivot_table(index=["method", "Method"], columns="metric", values="mean")
        .reset_index()
    )
    if {"mean_travel_time", "co2_g_per_km"} <= set(pts.columns):
        chart = (
            alt.Chart(pts)
            .mark_circle(size=120, stroke="#fcfcfb", strokeWidth=2)
            .encode(
                x=alt.X("co2_g_per_km:Q", title="CO2 (g/km)", scale=alt.Scale(zero=False)),
                y=alt.Y(
                    "mean_travel_time:Q", title="Mean travel time (s)", scale=alt.Scale(zero=False)
                ),
                color=alt.Color("Method:N", scale=color_scale(methods)),
                tooltip=[
                    "Method",
                    alt.Tooltip("co2_g_per_km:Q", format=".1f"),
                    alt.Tooltip("mean_travel_time:Q", format=".1f"),
                ],
            )
        )
        st.altair_chart(chart, width="stretch")
        st.caption("Lower-left is better on both criteria.")

with tab_training:
    logs = []
    for path in sorted(TRAINING_DIR.glob(f"*/{network}/seed*/episodes.csv")):
        ep = pd.read_csv(path)
        ep["variant"] = path.parent.parent.parent.name
        ep["seed"] = path.parent.name
        logs.append(ep)
    if not logs:
        st.info("No training log for this network.")
    else:
        ep = pd.concat(logs, ignore_index=True)
        level = st.selectbox(
            "Demand level of the training episodes", sorted(ep["episode_demand"].unique())
        )
        ep = ep[ep["episode_demand"] == level]
        ep["Variant"] = ep["variant"].map(label) + " / " + ep["seed"]
        chart = (
            alt.Chart(ep)
            .mark_line(strokeWidth=2, point=True)
            .encode(
                x=alt.X("timesteps:Q", title="Training steps"),
                y=alt.Y("mean_halting:Q", title="Halting vehicles at the signals"),
                color="Variant:N",
                tooltip=["Variant", "timesteps", alt.Tooltip("mean_halting:Q", format=".1f")],
            )
        )
        st.altair_chart(chart, width="stretch")

with tab_decisions:
    files = sorted((LOGS_DIR / "decisions").glob("explained__*.csv"))
    if not files:
        st.info("No decision log yet. Run `python -m cotraffic explain`.")
    else:
        choice = st.selectbox(
            "Episode", files, format_func=lambda p: p.stem.replace("explained__", "")
        )
        log = pd.read_csv(choice)
        agent = st.selectbox("Intersection", sorted(log["agent"].unique()))
        sub = log[log["agent"] == agent]
        t = st.slider(
            "Time (s)",
            int(sub["time"].min()),
            int(sub["time"].max()),
            int(sub["time"].min()),
            step=5,
        )
        window = sub[(sub["time"] >= t) & (sub["time"] < t + 120)]
        st.dataframe(
            window[["time", "requested", "executed", "shield", "depends_on", "explanation"]],
            width="stretch",
            hide_index=True,
        )
