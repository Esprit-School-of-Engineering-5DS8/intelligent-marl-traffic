#!/usr/bin/env python3
"""train_ev_rl.py
Fitted Q-iteration over EV priority decision episodes (M4).

Loads episode CSVs collected by `experiments/run_ev_priority.py --mode rl`,
trains one value regressor per strategy, and saves the policy artifact.

Usage:
    python experiments/train_ev_rl.py --data "results/ev/3x3_rl*_episodes.csv"
"""

import os
import sys
import glob
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from forecasting.ev_arrival_predictor import FEATURE_COLUMNS
from agents.emergency_rl import EVRLPolicy, STRATEGY_NAMES, DEFAULT_POLICY_PATH


def main():
    parser = argparse.ArgumentParser(description="Train the EV priority RL policy")
    parser.add_argument("--data", default="results/ev/3x3_rl*_episodes.csv")
    parser.add_argument("--out", default=DEFAULT_POLICY_PATH)
    parser.add_argument("--margin", type=float, default=5.0,
                        help="Required predicted advantage over the reference strategy "
                             "before deviating from it")
    parser.add_argument("--reference-action", type=int, default=None,
                        help="Strategy used when the margin is not met "
                             "(default: best fixed strategy found in the data)")
    args = parser.parse_args()

    files = sorted(glob.glob(args.data))
    if not files:
        raise FileNotFoundError(f"No episode files match '{args.data}'")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    print(f"[ev_rl] {len(files)} episode files | {len(df)} episodes")
    print("\nper-strategy data:")
    for action, group in df.groupby("action"):
        print(f"  {action} {STRATEGY_NAMES[int(action)]:8} n={len(group):4d}  "
              f"mean reward={group['reward'].mean():8.2f}  "
              f"mean EV delay={group['ev_delay_s'].mean():6.2f}s")

    df = df.copy()
    df["action_feat"] = df["action"]
    actions = sorted(df["action"].unique())
    model = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                      learning_rate=0.05, subsample=0.8,
                                      random_state=42)
    model.fit(df[FEATURE_COLUMNS + ["action_feat"]], df["reward"])

    x = df[FEATURE_COLUMNS]
    q = np.column_stack([model.predict(x.assign(action_feat=a)) for a in actions])
    fixed_means = df.groupby("action")["reward"].mean()
    best_fixed_action = int(fixed_means.idxmax())
    reference = args.reference_action if args.reference_action is not None else best_fixed_action
    ref_index = actions.index(reference)

    raw_choices = q.argmax(axis=1)
    margin_choices = np.where(
        q.max(axis=1) >= q[:, ref_index] + args.margin, raw_choices, ref_index)
    raw_value = q[np.arange(len(q)), raw_choices].mean()
    margin_value = q[np.arange(len(q)), margin_choices].mean()
    deviation_share = float((margin_choices != ref_index).mean())

    print(f"\nbest fixed strategy    : {STRATEGY_NAMES[best_fixed_action]} "
          f"(mean reward {fixed_means.max():.2f})")
    print(f"raw argmax in-sample   : {raw_value:.2f} (optimistic)")
    print(f"margin policy in-sample: {margin_value:.2f} "
          f"(margin={args.margin}, reference={STRATEGY_NAMES[reference]}, "
          f"deviations={deviation_share:.1%})")
    print("real check is online evaluation")

    EVRLPolicy(model, actions=actions, margin=args.margin,
               reference_action=reference).save(args.out)


if __name__ == "__main__":
    main()
