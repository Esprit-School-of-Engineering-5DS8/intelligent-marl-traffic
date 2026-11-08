"""Export the project's results as the JSON files the dashboard reads.

Everything comes from files the experiments wrote (nothing is computed from scratch here
except averages over seeds and histogram sums):

    results/summary/summary.csv, comparisons_*.csv, run_counts.csv   -> summary, comparisons
    results/logs/timeseries/*.csv                                    -> per-minute curves
    results/logs/waiting_distributions/*.csv                         -> waiting histograms
    results/logs/decisions/explained__*.csv                          -> explained decisions
    results/training/<agent>/<network>/seed*/episodes.csv            -> learning curves
    results/extra/raw, results/extra/logs                            -> pedestrian and
                                                                        emergency details
    networks/<name>/<name>.net.xml                                   -> map geometry

    python scripts/export_dashboard_data.py [--out frontend/public/data] [--skip-networks]

The FastAPI backend (api/) serves the same files, so both data sources of the dashboard
show identical numbers.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cotraffic import config
from cotraffic.networks.build import net_file
from cotraffic.paths import RESULTS_DIR

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "frontend" / "public" / "data"
SUMMARY = RESULTS_DIR / "summary"
LOGS = RESULTS_DIR / "logs"
EXTRA = RESULTS_DIR / "extra"
TRAINING = RESULTS_DIR / "training"
# The networks that exist, read from configs/networks rather than repeated here: an
# exporter with its own list keeps serving a network whose config was deleted.
NETWORKS = config.available("networks")
RUN_ID = re.compile(r"^(?P<method>[^_]+(?:_[^_]+)*?)__(?P<network>[^_]+(?:_[^_]+)*?)__")


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def clean(value: Any) -> Any:
    """JSON has no NaN or infinity: missing values become null."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def write(out: Path, name: str, payload: Any) -> None:
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(payload), separators=(",", ":")), encoding="utf-8")
    print(f"  {path.relative_to(out)}  {path.stat().st_size / 1024:.0f} kB")


def split_run_id(run_id: str) -> dict[str, Any]:
    method, network, scenario, demand, seed = run_id.split("__")
    return {
        "method": method,
        "network": network,
        "scenario": scenario,
        "demand": demand,
        "seed": int(seed.lstrip("s")),
    }


def method_of(run_ids: pd.Series) -> pd.Series:
    """Controller of each run; learned ones carry their training run ("coop_full-t2")."""
    return run_ids.str.split("__").str[0].str.replace(r"-t\d+$", "", regex=True)


def cell_key(network: str, scenario: str, demand: str) -> str:
    return f"{network}__{scenario}__{demand}"


# --- aggregated results -----------------------------------------------------------------


SUMMARY_COLUMNS = [
    "network",
    "scenario",
    "demand",
    "method",
    "metric",
    "n",
    "n_train",
    "mean",
    "ci_lo",
    "ci_hi",
    "std",
]


def load_exported_summary(out: Path) -> pd.DataFrame | None:
    """The aggregate table already exported to the dashboard, in the study's schema."""
    path = out / "summary.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows).rename(columns={"ciLo": "ci_lo", "ciHi": "ci_hi", "nTrain": "n_train"})
    for column in SUMMARY_COLUMNS:
        if column not in frame:
            frame[column] = None
    return frame[SUMMARY_COLUMNS]


def export_summary(out: Path) -> pd.DataFrame:
    path = SUMMARY / "summary.csv"
    if path.exists():
        summary = pd.read_csv(path)
    else:
        # A checkout without the study's aggregates must not blank the dashboard: recording
        # a replay refreshes the export, and that must not delete rows it cannot rebuild.
        existing = load_exported_summary(out)
        if existing is not None:
            print(f"  no aggregated summary at {path}; keeping the {len(existing)} exported rows")
            return existing
        print(f"  no aggregated summary at {path}; writing an empty table")
        summary = pd.DataFrame(columns=SUMMARY_COLUMNS)
    extra = extra_summary()
    if not extra.empty:
        summary = pd.concat([summary, extra], ignore_index=True)
    rows = [
        {camel(k): v for k, v in rec.items()}
        for rec in summary[SUMMARY_COLUMNS].to_dict("records")
    ]
    write(out, "summary.json", rows)
    return summary


def extra_summary() -> pd.DataFrame:
    """Means and normal-approximation 95 % intervals over seeds for the extra runs' new
    metrics (pedestrian P95, crossings in green, ETA error...). The report's tables keep
    their bootstrap intervals; these metrics are not in them."""
    raw_dir = EXTRA / "raw"
    if not raw_dir.exists():
        return pd.DataFrame()
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    runs = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    metrics = [
        "ped_p95_waiting_time",
        "ped_crossings_in_green_pct",
        "ped_green_slope_s_per_person",
        "ev_stops_at_red_mean",
        "ev_eta_error_mean_s",
        "ev_eta_abs_error_mean_s",
        "reward_delay",
        "reward_co2",
        "reward_ev",
        "reward_ped",
    ]
    rows = []
    for (network, scenario, demand, method), group in runs.groupby(
        ["network", "scenario", "demand", "method"]
    ):
        for metric in metrics:
            if metric not in group:
                continue
            values = group[metric].dropna()
            if values.empty:
                continue
            mean = float(values.mean())
            std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            half = 1.96 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
            rows.append(
                {
                    "network": network,
                    "scenario": scenario,
                    "demand": demand,
                    "method": method,
                    "metric": metric,
                    "n": len(values),
                    "n_train": 1 if method not in BASELINE_SET else 0,
                    "mean": mean,
                    "ci_lo": mean - half,
                    "ci_hi": mean + half,
                    "std": std,
                }
            )
    return pd.DataFrame(rows)


BASELINE_SET = {"ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp"}


def export_comparisons(out: Path) -> None:
    frames = [pd.read_csv(f) for f in sorted(SUMMARY.glob("comparisons_*.csv"))]
    if not frames:
        # Same rule as the summary: never replace exported comparisons we cannot rebuild.
        if (out / "comparisons.json").exists():
            print("  no comparison tables; keeping comparisons.json")
            return
        write(out, "comparisons.json", [])
        return
    comp = pd.concat(frames, ignore_index=True)
    keep = [
        "network",
        "scenario",
        "demand",
        "method",
        "reference",
        "metric",
        "mean",
        "reference_mean",
        "improvement_pct",
        "paired_improvement_pct",
        "paired_ci_lo",
        "paired_ci_hi",
        "p_value",
        "p_holm",
        "cliffs_delta",
        "effect",
        "significant",
        "n",
        "comparison",
        "family",
    ]
    comp = comp[[c for c in keep if c in comp.columns]]
    rows = [{camel(k): v for k, v in rec.items()} for rec in comp.to_dict("records")]
    for row in rows:
        row["significant"] = bool(row["significant"])
    write(out, "comparisons.json", rows)


# --- per-run logs ------------------------------------------------------------------------


def export_timeseries(out: Path) -> list[str]:
    """Per-minute network state, averaged over the seeds of each controller."""
    groups: dict[str, list[pd.DataFrame]] = {}
    for f in sorted((LOGS / "timeseries").glob("*.csv")):
        groups.setdefault("__".join(f.stem.split("__")[1:4]), []).append(f)
    cells = []
    for key, files in groups.items():
        series = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
        series["method"] = method_of(series["run_id"])
        cols = [c for c in series.columns if c not in ("run_id", "method", "minute")]
        mean = series.groupby(["method", "minute"])[cols].mean().reset_index()
        payload: dict[str, Any] = {
            "cell": dict(zip(["network", "scenario", "demand"], key.split("__"), strict=True)),
            "methods": {},
        }
        for method, g in mean.groupby("method"):
            g = g.sort_values("minute")
            payload["methods"][method] = {
                "minute": g["minute"].astype(int).tolist(),
                **{camel(c): g[c].round(3).tolist() for c in cols},
            }
        write(out, f"timeseries/{key}.json", payload)
        cells.append(key)
    return cells


def export_distributions(out: Path) -> None:
    """Waiting-time histograms (vehicles per 15 s bin), summed over seeds."""
    groups: dict[str, list[Path]] = {}
    for f in sorted((LOGS / "waiting_distributions").glob("*.csv")):
        groups.setdefault("__".join(f.stem.split("__")[1:4]), []).append(f)
    for key, files in groups.items():
        dist = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
        dist["method"] = method_of(dist["run_id"])
        seeds = dist.groupby("method")["run_id"].nunique()
        hist = dist.groupby(["method", "wait_from_s", "wait_to_s"])["vehicles"].sum().reset_index()
        payload = {
            "cell": dict(zip(["network", "scenario", "demand"], key.split("__"), strict=True)),
            "methods": {
                method: {
                    "from": g["wait_from_s"].tolist(),
                    "to": g["wait_to_s"].tolist(),
                    # per run, so controllers with more seeds are not inflated
                    "vehicles": (g["vehicles"] / seeds[method]).round(2).tolist(),
                }
                for method, g in hist.groupby("method")
            },
        }
        write(out, f"distributions/{key}.json", payload)


def export_decisions(out: Path) -> list[dict[str, Any]]:
    """Explained decisions of the learned controllers (one evaluation run each)."""
    index = []
    for f in sorted((LOGS / "decisions").glob("explained__*.csv")):
        run_id = f.stem.removeprefix("explained__")
        meta = split_run_id(run_id)
        dec = pd.read_csv(f)
        dec = dec.fillna("")
        payload = {
            "runId": run_id,
            **meta,
            "agents": sorted(dec["agent"].unique().tolist()),
            "time": dec["time"].tolist(),
            "agent": dec["agent"].tolist(),
            "requested": dec["requested"].astype(int).tolist(),
            "executed": dec["executed"].astype(int).tolist(),
            "shield": dec["shield"].astype(str).tolist(),
            "dependsOn": dec["depends_on"].astype(str).tolist(),
            "explanation": dec["explanation"].astype(str).tolist(),
        }
        write(out, f"decisions/{run_id}.json", payload)
        index.append({"runId": run_id, **meta, "decisions": len(dec)})
    return index


def export_training(out: Path) -> list[dict[str, Any]]:
    """Learning curves: one point per training episode, per seed."""
    index = []
    for agent_dir in sorted(
        p for p in TRAINING.iterdir() if p.is_dir() and not p.name.startswith("_")
    ):
        for net_dir in sorted(p for p in agent_dir.iterdir() if p.is_dir()):
            runs = []
            for seed_dir in sorted(net_dir.glob("seed*")):
                ep = seed_dir / "episodes.csv"
                if not ep.exists():
                    continue
                df = pd.read_csv(ep)
                if df.empty:
                    continue
                info_file = seed_dir / "run_info.json"
                info = json.loads(info_file.read_text()) if info_file.exists() else {}
                runs.append(
                    {
                        "seed": int(seed_dir.name.removeprefix("seed")),
                        "totalTimesteps": info.get("total_timesteps"),
                        "algorithm": info.get("config", {}).get("algorithm", "ppo"),
                        "timesteps": df["timesteps"].astype(int).tolist(),
                        "episodeReward": df["episode_reward"].round(4).tolist(),
                        "meanHalting": df["mean_halting"].round(3).tolist(),
                        "demand": df["episode_demand"].astype(str).tolist(),
                        "switches": df["switches"].astype(int).tolist(),
                        "shieldMinGreen": df.get("shield_min_green", pd.Series(dtype=int))
                        .astype(int)
                        .tolist(),
                    }
                )
            if runs:
                payload = {"agent": agent_dir.name, "network": net_dir.name, "runs": runs}
                write(out, f"training/{agent_dir.name}__{net_dir.name}.json", payload)
                index.append(
                    {
                        "agent": agent_dir.name,
                        "network": net_dir.name,
                        "seeds": [r["seed"] for r in runs],
                        "episodes": sum(len(r["timesteps"]) for r in runs),
                    }
                )
    return index


def export_pedestrian_greens(out: Path) -> None:
    """Every pedestrian green of the extra runs: crowd at its start, its length, crossings."""
    folder = EXTRA / "logs" / "pedestrian_greens"
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    if not files:
        write(out, "pedestrian_greens.json", {"cells": {}})
        return
    log = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    meta = log["run_id"].str.split("__", expand=True)
    log["method"], log["network"], log["demand"] = method_of(log["run_id"]), meta[1], meta[3]
    cells: dict[str, Any] = {}
    for (network, demand), g in log.groupby(["network", "demand"]):
        methods = {}
        for method, m in g.groupby("method"):
            # waiting crowd -> mean green length (the slope the report discusses)
            stats = (
                m.groupby(m["waiting_at_start"].clip(upper=20).round())["duration_s"]
                .agg(["mean", "size"])
                .reset_index()
            )
            # crowd sizes seen fewer than 10 times give noisy means: left out
            stats = stats[stats["size"] >= 10]
            methods[method] = {
                "greens": len(m),
                "crossed": int(m["crossed"].sum()),
                "crowd": stats["waiting_at_start"].astype(int).tolist(),
                "meanDuration": stats["mean"].round(2).tolist(),
                "count": stats["size"].astype(int).tolist(),
            }
        cells[f"{network}__pedestrians__{demand}"] = methods
    write(out, "pedestrian_greens.json", {"cells": cells})


def export_emergency_log(out: Path) -> None:
    """Every emergency vehicle of the extra runs: stops at red, ETA and its error."""
    folder = EXTRA / "logs" / "emergency"
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    if not files:
        write(out, "emergency_log.json", {"vehicles": []})
        return
    log = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    meta = log["run_id"].str.split("__", expand=True)
    log.insert(1, "method", method_of(log["run_id"]))
    log.insert(2, "network", meta[1])
    log.insert(3, "scenario", meta[2])
    log.insert(4, "demand", meta[3])
    log.insert(5, "seed", meta[4].str.lstrip("s").astype(int))
    rows = [{camel(k): v for k, v in rec.items()} for rec in log.to_dict("records")]
    write(out, "emergency_log.json", {"vehicles": rows})


# --- network geometry --------------------------------------------------------------------


def export_network(out: Path, name: str) -> dict[str, Any] | None:
    import sumolib

    path = net_file(name)
    if not path.exists():
        print(f"  (no {path.name}: skipped)")
        return None
    net = sumolib.net.readNet(str(path), withInternal=True, withPedestrianConnections=True)

    def pts(shape: list[tuple[float, float]]) -> list[list[float]]:
        return [[round(x, 1), round(y, 1)] for x, y, *_ in shape]

    lanes = []
    for edge in net.getEdges(withInternal=True):
        function = edge.getFunction()
        if function in ("walkingarea",):
            continue
        for lane in edge.getLanes():
            allowed = lane.getPermissions()
            ped = "pedestrian" in allowed
            road = any(v in allowed for v in ("passenger", "bus", "emergency"))
            if not ped and not road:
                continue
            lanes.append(
                {
                    "id": lane.getID(),
                    "edge": edge.getID(),
                    "shape": pts(lane.getShape()),
                    "width": round(lane.getWidth(), 2),
                    "allows": "both" if ped and road else ("pedestrian" if ped else "vehicle"),
                    "kind": "crossing"
                    if function == "crossing"
                    else ("internal" if function == "internal" else "normal"),
                }
            )
    junctions = []
    for node in net.getNodes():
        if node.getType() == "internal":
            continue
        shape = node.getShape()
        junctions.append(
            {
                "id": node.getID(),
                "position": [round(node.getCoord()[0], 1), round(node.getCoord()[1], 1)],
                "signalised": node.getType().startswith("traffic_light"),
                "shape": pts(shape) if shape else [],
            }
        )
    signals = []
    for tls in net.getTrafficLights():
        links = []
        for in_lane, _out_lane, index in tls.getConnections():
            shape = in_lane.getShape()
            links.append({"index": index, "lane": in_lane.getID(), "position": pts([shape[-1]])[0]})
        links.sort(key=lambda link: link["index"])
        signals.append({"tls": tls.getID(), "links": links})
    (x0, y0), (x1, y1) = net.getBBoxXY()
    payload = {
        "network": name,
        "bounds": [[round(x0, 1), round(y0, 1)], [round(x1, 1), round(y1, 1)]],
        "lanes": lanes,
        "junctions": junctions,
        "signals": signals,
    }
    write(out, f"networks/{name}.json", payload)
    return {"network": name, "lanes": len(lanes), "signals": len(signals)}


# --- index ------------------------------------------------------------------------------


def export_meta(out: Path, summary: pd.DataFrame, extras: dict[str, Any]) -> None:
    cells = (
        summary.groupby(["network", "scenario", "demand"])["method"]
        .apply(lambda m: sorted(set(m)))
        .reset_index()
    )
    counts = (
        pd.read_csv(SUMMARY / "run_counts.csv") if (SUMMARY / "run_counts.csv").exists() else None
    )
    extra_runs = len(list((EXTRA / "raw").glob("*.csv"))) if (EXTRA / "raw").exists() else 0
    replays = []
    for path in sorted((out / "replays").glob("*.json")) if (out / "replays").exists() else []:
        rec = json.loads(path.read_text(encoding="utf-8"))
        replays.append(
            {
                "id": rec["id"],
                "left": rec["sides"]["left"]["method"],
                "right": rec["sides"]["right"]["method"],
                "window": rec["window"],
            }
        )
    payload = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "cells": [
            {"network": r.network, "scenario": r.scenario, "demand": r.demand, "methods": r.method}
            for r in cells.itertuples()
        ],
        "methods": sorted(summary["method"].unique().tolist()),
        "metrics": sorted(summary["metric"].unique().tolist()),
        "runs": int(counts["runs"].sum()) if counts is not None and "runs" in counts else None,
        "extraRuns": extra_runs,
        "dqnAvailable": bool((summary["method"] == "dqn").any()),
        "replays": replays,
        **extras,
    }
    write(out, "meta.json", payload)


def prune_stale(out: Path, networks: Sequence[str]) -> list[str]:
    """Delete the exported files of networks that no longer exist in ``configs/networks``.

    Every generated file carries its network in its name, so removing a network otherwise
    leaves its JSON behind for ever and the dashboard keeps offering scenarios that no run
    can produce any more (the old grid4x4 and grid8x8 grids).
    """
    known = set(networks)
    targets: list[tuple[Path, int]] = []
    # Index of the network inside each file's name: the per-cell files are named
    # <network>__<scenario>__<demand>, the per-run ones keep the run id, in which the
    # method comes first and the network second.
    for folder, index in (
        ("timeseries", 0),
        ("distributions", 0),
        ("decisions", 1),
        ("training", 1),
        ("replays", 0),
    ):
        directory = out / folder
        if directory.is_dir():
            targets += [(p, index) for p in sorted(directory.glob("*.json"))]
    network_dir = out / "networks"
    if network_dir.is_dir():
        targets += [(p, -1) for p in sorted(network_dir.glob("*.json"))]
    removed = []
    for path, index in targets:
        parts = path.stem.split("__")
        name = path.stem if index == -1 else (parts[index] if len(parts) > index else None)
        if not name or name in known:
            continue
        path.unlink()
        removed.append(str(path.relative_to(out)))
    return removed


# --- runs registry (the experiment-platform core) ----------------------------------------

# Metrics the runs table shows as flat columns; anything else stays in the drawer.
RUN_COLUMNS = [
    "mean_waiting_time", "throughput_per_h", "co2_total_kg",
    "teleports_total", "stops_per_vehicle", "emergency_stops", "ev_red_stops",
]

# The registry is model-centric: scripted baselines + LLM + the generalist only.
# The ablation variants (coop_ped, coop_ev, coop_full, ind_*, dqn, ...) stay in
# summary.json / comparatives for the study's attribution analysis; they are
# deliberately excluded here so the Runs/Models pages never present them as models.
REGISTRY_METHODS = frozenset({
    "ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp", "llm", "generalist",
})


def _registry_method(name: str) -> bool:
    return name in REGISTRY_METHODS or name.startswith("generalist")


def export_run_registry(out: Path, summary: pd.DataFrame) -> dict[str, Any]:
    """One Run entity per training seed and per evaluation cell, as runs.json.

    MLflow's mental model: every job is a run with an identity, its metrics, its
    hyperparameters and its artifacts, not a metric-row permutation. The registry merges
    (a) the training runs found under results/training and (b) the evaluation cells of
    summary.csv, so the dashboard table has one row per thing that was launched.
    """
    runs_index: dict[str, dict[str, Any]] = {}

    #Runs deleted from the dashboard stay deleted across re-exports.
    tombstone_path = ROOT / "results" / "registry_hidden.json"
    hidden: set[str] = set()
    if tombstone_path.is_file():
        try:
            hidden = set(json.loads(tombstone_path.read_text()))
        except (OSError, ValueError):
            hidden = set()

    for agent_dir in sorted(p for p in TRAINING.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for net_dir in sorted(p for p in agent_dir.iterdir() if p.is_dir()):
            for seed_dir in sorted(net_dir.glob("seed*")):
                ep = seed_dir / "episodes.csv"
                if not ep.exists():
                    continue
                df = pd.read_csv(ep)
                if df.empty:
                    continue
                info_file = seed_dir / "run_info.json"
                info = json.loads(info_file.read_text()) if info_file.exists() else {}
                hp = info.get("config", {}) or {}
                seed = int(seed_dir.name.removeprefix("seed"))
                run_id = f"train__{agent_dir.name}__{net_dir.name}__s{seed}"
                if run_id in hidden:
                    continue
                is_current_policy = agent_dir.name.startswith("generalist") or agent_dir.name in {"rl", "rl_shortpilot"}
                runs_index[run_id] = {
                    "runId": run_id,
                    "name": f"{agent_dir.name} · {net_dir.name} · seed {seed}",
                    "kind": "training",
                    "method": "generalist" if agent_dir.name.startswith("generalist") else agent_dir.name,
                    "legacy": not is_current_policy,
                    "legacyReason": "historical specialist or ablation run; retained but hidden by default" if not is_current_policy else None,
                    "source": "historical_training_export",
                    "type": "rl",
                    "model": None,
                    "network": net_dir.name,
                    "seed": seed,
                    "seeds": [seed],
                    "hyperparameters": {k: v for k, v in hp.items() if isinstance(v, (int, float, str, bool))},
                    "status": "finished",
                    "algorithm": info.get("config", {}).get("algorithm", "ppo"),
                    "totalTimesteps": info.get("total_timesteps"),
                    "episodes": len(df),
                    "finalReward": round(float(df["episode_reward"].tail(20).mean()), 4),
                    "metrics": {"episodeReward": round(float(df["episode_reward"].tail(20).mean()), 4)},
                    "artifacts": {
                        "curves": f"training/{agent_dir.name}__{net_dir.name}",
                        "checkpoint": str(seed_dir.name),
                    },
                }

    eval_metrics = summary[summary["metric"].isin(RUN_COLUMNS)][
        ["network", "scenario", "demand", "method", "metric", "mean", "ci_lo", "ci_hi", "n"]
    ]
    raw_root = ROOT / "results" / "raw"
    raw_parts = []
    for raw_file in sorted(raw_root.glob("*.csv")):
        try:
            frame = pd.read_csv(raw_file)
            if {"network", "scenario", "demand", "method", "seed"}.issubset(frame.columns):
                raw_parts.append(frame)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
    raw_data = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    for (network, scenario, demand, method), group in eval_metrics.groupby(
        ["network", "scenario", "demand", "method"]
    ):
        is_current_policy = _registry_method(str(method))
        metrics: dict[str, Any] = {}
        stats: dict[str, dict[str, Any]] = {}
        for rec in group.to_dict("records"):
            metrics[rec["metric"]] = rec["mean"]
            stats[rec["metric"]] = {
                "ciLo": rec["ci_lo"], "ciHi": rec["ci_hi"], "n": rec["n"]
            }
        raw_cell = raw_data[(raw_data.network == network) & (raw_data.scenario == scenario) & (raw_data.demand == demand) & (raw_data.method == method)] if not raw_data.empty else pd.DataFrame()
        seeds = sorted(int(seed) for seed in raw_cell["seed"].dropna().unique()) if "seed" in raw_cell else []
        if not raw_cell.empty:
            for metric in RUN_COLUMNS:
                if metric in raw_cell:
                    values = pd.to_numeric(raw_cell[metric], errors="coerce").dropna()
                    if not values.empty:
                        metrics[metric] = float(values.mean())
                        stats[metric] = {"ciLo": float(values.mean() - 1.96 * values.std(ddof=1) / len(values) ** 0.5) if len(values) > 1 else float(values.iloc[0]), "ciHi": float(values.mean() + 1.96 * values.std(ddof=1) / len(values) ** 0.5) if len(values) > 1 else float(values.iloc[0]), "n": len(values)}
        kind = "evaluation"
        run_id = f"eval__{method}__{network}__{scenario}__{demand}"
        if run_id in hidden:
            continue
        runs_index[run_id] = {
            "runId": run_id,
            "name": f"{method} · {network} · {scenario} · {demand}",
            "kind": kind,
            "legacy": not is_current_policy,
            "legacyReason": "historical specialist or ablation run; retained but hidden by default" if not is_current_policy else None,
            "source": "historical_evaluation_export",
            "type": "eval",
            "model": None,
            "network": network,
            "scenario": scenario,
            "demand": demand,
            "method": method,
            "seed": None,
            "seeds": sorted(set(seeds)),
            "hyperparameters": {},
            "status": "finished",
            "episodes": None,
            "metrics": metrics,
            "metricStats": stats,
            "artifacts": {},
        }

    payload = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "columns": RUN_COLUMNS,
        "runs": sorted(runs_index.values(), key=lambda r: (r["kind"], r["runId"])),
    }
    write(out, "runs.json", payload)
    return {"runs": len(runs_index)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-networks", action="store_true")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    print(f"exporting to {out} (networks: {', '.join(NETWORKS)})")
    for name in prune_stale(out, NETWORKS):
        print(f"  pruned {name} (network no longer exists)")
    summary = export_summary(out)
    export_comparisons(out)
    timeseries = export_timeseries(out)
    export_distributions(out)
    decisions = export_decisions(out)
    training = export_training(out)
    export_pedestrian_greens(out)
    export_emergency_log(out)
    registry = export_run_registry(out, summary)
    networks = []
    if not args.skip_networks:
        for name in NETWORKS:
            info = export_network(out, name)
            if info:
                networks.append(info)
    elif (out / "networks").exists():
        networks = [{"network": p.stem} for p in sorted((out / "networks").glob("*.json"))]
    export_meta(
        out,
        summary,
        {
            "timeseries": timeseries,
            "decisions": decisions,
            "training": training,
            "networks": networks,
            "registry": registry,
        },
    )


if __name__ == "__main__":
    main()
