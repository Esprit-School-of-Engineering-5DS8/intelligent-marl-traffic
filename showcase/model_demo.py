#!/usr/bin/env python3
"""model_demo.py
Offline showcase of the ETA model and red-arrival classifier on held-out data.
"""
import os
import sys
import glob

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from forecasting.ev_arrival_predictor import (EVArrivalPredictor, FEATURE_COLUMNS,
                                              physics_eta)


def main():
    files = sorted(glob.glob(os.path.join(PROJECT_ROOT, "results", "ev", "3x3_*_eta.csv")))
    if not files:
        raise SystemExit("No ETA data found. Run a collection first (see showcase/README.md)")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    tags = sorted(df["run_tag"].unique())
    test = df[df["run_tag"].isin(tags[::4])]
    predictor = EVArrivalPredictor().load()

    def show(title, row):
        features = {key: row[key] for key in FEATURE_COLUMNS}
        eta = predictor.predict(features)
        prob = predictor.predict_red_prob(features)
        physics = physics_eta(row)
        print(title)
        print(f"  input : dist={row['distance_m']:6.0f}m  speed={row['speed_m_s']:5.1f}m/s  "
              f"vehicles_on_lane={int(row['lane_vehicles'])}  "
              f"signal={int(row['signal_state'])}  "
              f"switch_in={row['time_to_switch_s']:5.1f}s  rank={int(row['rank'])}")
        print(f"  model : ETA {eta:5.1f}s   P(arrive on red) {prob:.2f}")
        print(f"  truth : actual {row['label_s']:5.1f}s   arrived_on_red={int(row['arrive_red'])}"
              f"   physics guess {physics:5.1f}s")
        print()

    stopped = test[(test["rank"] == 1) & (test["signal_state"] == 0) & (test["speed_m_s"] < 1)]
    rolling = test[(test["rank"] == 1) & (test["signal_state"] == 2) & (test["distance_m"] > 100)]
    second = test[(test["rank"] == 2) & (test["distance_m"] > 250)]
    if len(stopped):
        show("Example 1 - next light, stopped at red", stopped.iloc[0])
    if len(rolling):
        show("Example 2 - next light, rolling toward green", rolling.iloc[0])
    if len(second):
        show("Example 3 - second light ahead", second.iloc[0])

    err = np.abs(predictor.model.predict(test[FEATURE_COLUMNS]) - test["label_s"].to_numpy())
    rank1 = (test["rank"] == 1).to_numpy()
    rank2 = (test["rank"] == 2).to_numpy()
    print("Held-out summary (runs never seen in training):")
    print(f"  ETA MAE next light : {err[rank1].mean():.2f}s")
    print(f"  ETA MAE 2nd light  : {err[rank2].mean():.2f}s")


if __name__ == "__main__":
    main()
