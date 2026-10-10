#!/usr/bin/env python3
"""make_report_figures.py
Generates showcase figures and the results table from results/ev data
(3x3 scene, seed 42) and the saved models.
"""

import os
import sys
import glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import GradientBoostingRegressor

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from forecasting.ev_arrival_predictor import (EVArrivalPredictor, FEATURE_COLUMNS,
                                              physics_eta)
from agents.emergency_rl import STRATEGY_NAMES

RESULTS = os.path.join(PROJECT_ROOT, "results", "ev")
OUT = os.path.join(PROJECT_ROOT, "showcase", "figures")
os.makedirs(OUT, exist_ok=True)

COLORS = ["#8d99ae", "#8d99ae", "#2a9d8f", "#457b9d"]


def load_runs():
    df = pd.read_csv(os.path.join(RESULTS, "summary.csv"))
    df = df[(df["scenario"] == "3x3") & (df["seed"] == 42) & (df["steps"] == 3600)]
    runs = {
        "Fixed-time": df[df["mode"] == "fixed"].iloc[-1],
        "Max-pressure": df[df["mode"] == "max_pressure"].iloc[-1],
        "Priority (rule)": df[(df["mode"] == "priority")
                              & (df["ev_activation_distance_m"] == 150)
                              & df["ev_eta_trigger_s"].isna()].iloc[-1],
        "RL (safe)": df[df["mode"] == "rl"].iloc[-1],
    }
    return runs


def fig_ev_time(runs):
    fig, ax = plt.subplots(figsize=(6, 4))
    names = list(runs)
    values = [runs[name]["ev_mean_duration_s"] for name in names]
    ax.bar(names, values, color=COLORS)
    for i, value in enumerate(values):
        ax.text(i, value + 0.6, f"{value:.1f}", ha="center")
    ax.set_ylabel("Ambulance mean travel time (s)")
    ax.set_title("Ambulance travel time - 3x3 grid, one hour, seed 42")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1_ev_time.png"), dpi=150)
    plt.close(fig)


def fig_impact(runs):
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    names = list(runs)
    axes[0].bar(names, [runs[n]["civilian_mean_wait_per_veh_s"] for n in names], color=COLORS)
    axes[0].set_ylabel("Civilian mean wait (s per vehicle)")
    axes[0].set_title("Civilian cost")
    axes[1].bar(names, [runs[n]["ev_arrivals_on_green_pct"] for n in names], color=COLORS)
    axes[1].set_ylabel("Ambulance arrivals on green (%)")
    axes[1].set_title("Ambulance service")
    for ax in axes:
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig2_impact.png"), dpi=150)
    plt.close(fig)


def model_metrics():
    df = pd.concat([pd.read_csv(f) for f in sorted(
        glob.glob(os.path.join(RESULTS, "3x3_*_eta.csv")))], ignore_index=True)
    tags = sorted(df["run_tag"].unique())
    test = df[df["run_tag"].isin(tags[::4])]
    predictor = EVArrivalPredictor().load()

    mae = {}
    predictions = {
        "physics": test[FEATURE_COLUMNS].apply(physics_eta, axis=1).to_numpy(),
        "model": predictor.model.predict(test[FEATURE_COLUMNS]),
    }
    for name, pred in predictions.items():
        err = np.abs(pred - test["label_s"].to_numpy())
        mae[name] = {int(rank): round(err[(test["rank"] == rank).to_numpy()].mean(), 2)
                     for rank in (1, 2)}

    probability = predictor.red_model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    y = test["arrive_red"].to_numpy()
    rank1 = (test["rank"] == 1).to_numpy()
    far = rank1 & (test["distance_m"] > 150).to_numpy()
    rank2 = (test["rank"] == 2).to_numpy()
    auc = {
        "next light": round(roc_auc_score(y[rank1], probability[rank1]), 3),
        "next light >150 m": round(roc_auc_score(y[far], probability[far]), 3),
        "second light": round(roc_auc_score(y[rank2], probability[rank2]), 3),
    }
    return mae, auc


def fig_models(mae, auc):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    ranks = [1, 2]
    x = np.arange(len(ranks))
    width = 0.35
    axes[0].bar(x - width / 2, [mae["physics"][r] for r in ranks], width,
                label="physics formula", color="#8d99ae")
    axes[0].bar(x + width / 2, [mae["model"][r] for r in ranks], width,
                label="model", color="#2a9d8f")
    axes[0].set_xticks(x, ["next light", "second light"])
    axes[0].set_ylabel("MAE (s)")
    axes[0].set_title("ETA prediction error (held-out)")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.3)
    axes[1].bar(list(auc), list(auc.values()), color="#457b9d")
    axes[1].axhline(0.5, color="black", lw=1, ls="--")
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("AUC")
    axes[1].set_title("Red-arrival classifier (held-out)")
    axes[1].tick_params(axis="x", rotation=15)
    axes[1].grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_models.png"), dpi=150)
    plt.close(fig)


def fig_rl():
    files = sorted(glob.glob(os.path.join(RESULTS, "3x3_rl*_episodes.csv")))
    if not files:
        print(f"no RL episode data found, skipping {os.path.join(OUT, 'fig4_rl.png')}")
        return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df[~df["run_tag"].str.contains("eps0.0")]
    actions = sorted(df["action"].unique())
    means = df.groupby("action")["reward"].mean()
    counts = df.groupby("action")["reward"].size()

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    names = [STRATEGY_NAMES[a] for a in actions]
    colors = ["#2a9d8f" if a == int(means.idxmax()) else "#8d99ae" for a in actions]
    axes[0].bar(names, [means[a] for a in actions], color=colors)
    for i, a in enumerate(actions):
        axes[0].text(i, means[a] - 1.6, f"n={counts[a]}", ha="center", fontsize=8)
    axes[0].set_ylabel("Mean episode reward")
    axes[0].set_title(f"Observed reward per strategy ({len(df)} episodes)")
    axes[0].tick_params(axis="x", rotation=20)
    axes[0].grid(axis="y", alpha=0.3)

    tags = sorted(df["run_tag"].unique())
    test = df[df["run_tag"].isin(tags[::6])].copy()
    train = df[~df["run_tag"].isin(tags[::6])].copy()
    train["action_feat"] = train["action"]
    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                      subsample=0.8, random_state=42)
    model.fit(train[FEATURE_COLUMNS + ["action_feat"]], train["reward"])
    holdout = test[FEATURE_COLUMNS]
    q = np.column_stack([model.predict(holdout.assign(action_feat=a)) for a in actions])
    reference = actions.index(2)
    margins = [0, 2, 5, 8, 10, 15, 20, 30, 50]
    deviations, deltas = [], []
    for margin in margins:
        raw = q.argmax(axis=1)
        choice = np.where(q.max(axis=1) >= q[:, reference] + margin, raw, reference)
        deviations.append(100.0 * (choice != reference).mean())
        deltas.append(float((q[np.arange(len(q)), choice] - q[:, reference]).mean()))

    axes[1].bar([str(m) for m in margins], deviations, color="#e9c46a")
    axes[1].set_xlabel("safety margin (reward units)")
    axes[1].set_ylabel("deviations from best fixed (%)")
    twin = axes[1].twinx()
    twin.plot([str(m) for m in margins], deltas, color="#264653", marker="o")
    twin.axhline(0.0, color="black", lw=1, ls="--")
    twin.set_ylabel("predicted gain over best fixed (reward)")
    axes[1].set_title("Held-out margin sweep")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_rl.png"), dpi=150)
    plt.close(fig)


def main():
    runs = load_runs()
    fig_ev_time(runs)
    fig_impact(runs)
    mae, auc = model_metrics()
    fig_models(mae, auc)
    fig_rl()

    rows = [[name,
             run["ev_mean_duration_s"],
             run["ev_mean_waiting_s"],
             run["ev_red_stops_loop"],
             run["ev_arrivals_on_green_pct"],
             run["civilian_mean_wait_per_veh_s"],
             run["throughput"]]
            for name, run in runs.items()]
    table = pd.DataFrame(rows, columns=["Controller", "EV time (s)", "EV wait (s)",
                                        "Red stops", "Green arrivals (%)",
                                        "Civilian wait (s/veh)", "Throughput"])
    print(table.to_string(index=False))
    print(f"\nETA MAE by rank: {mae}")
    print(f"Classifier AUC: {auc}")
    print(f"figures written to {OUT}")


if __name__ == "__main__":
    main()
