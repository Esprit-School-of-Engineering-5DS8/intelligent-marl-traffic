"""Short-term inflow forecasting: next 5 minutes of arrivals on each approach.

Features at the end of minute t use only the past: the counts of minutes t-9..t and the
position of t in the demand hour. Target: vehicles arriving during minutes t+1..t+5.

Two splits, both free of leakage:

* chronological (main): models are fitted on the first two thirds of every run (minutes
  0-59 of the 90-minute evaluation protocol) and tested on the last third - forecasting
  the future of a known day;
* held-out realisations: fitted on some seeds, tested on other seeds - forecasting a
  day never seen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from cotraffic import config
from cotraffic.forecasting.dataset import DATA_DIR
from cotraffic.paths import SUMMARY_DIR

LAGS = 10
HORIZON = 5


SERIES = ["network", "demand", "seed", "tls", "side"]


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (run, approach, minute) with lag features and the 5-minute target."""
    warmup_min = float(config.load_protocol()["evaluation"]["warmup_s"]) / 60
    frames = []
    for key, g in df.groupby(SERIES, sort=False):
        g = g.sort_values("minute").set_index("minute")["vehicles"]
        g = g.reindex(range(int(g.index.min()), int(g.index.max()) + 1), fill_value=0.0)
        feats = pd.DataFrame({f"lag{k}": g.shift(k) for k in range(LAGS)})
        feats["target"] = sum(g.shift(-k) for k in range(1, HORIZON + 1))
        feats["hour_phase"] = (feats.index - warmup_min) / 60.0
        feats["minute"] = feats.index
        frames.append(feats.assign(**dict(zip(SERIES, key, strict=True))).reset_index(drop=True))
    return pd.concat(frames, ignore_index=True).dropna().reset_index(drop=True)


FEATURES = [f"lag{k}" for k in range(LAGS)] + ["hour_phase"]


def predict_all(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    lags5 = test[[f"lag{k}" for k in range(HORIZON)]].sum(axis=1).to_numpy()
    lags_all = test[[f"lag{k}" for k in range(LAGS)]].mean(axis=1).to_numpy() * HORIZON
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(train[FEATURES], train["target"])
    gbm = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=0)
    gbm.fit(train[FEATURES], train["target"])
    return {
        "persistence (last 5 min)": lags5,
        "moving average (last 10 min)": lags_all,
        "ridge regression": ridge.predict(test[FEATURES]),
        "gradient boosting": gbm.predict(test[FEATURES]),
    }


def _scores(test: pd.DataFrame, preds: dict[str, np.ndarray], split: str) -> list[dict]:
    rows = []
    for model, y_hat in preds.items():
        err = y_hat - test["target"].to_numpy()
        for demand, idx in [("all", np.arange(len(test)))] + [
            (d, np.where(test["demand"].to_numpy() == d)[0])
            for d in sorted(test["demand"].unique())
        ]:
            if idx.size == 0:
                continue
            rows.append(
                {
                    "split": split,
                    "model": model,
                    "demand": demand,
                    "n": int(idx.size),
                    "mae": float(np.mean(np.abs(err[idx]))),
                    "rmse": float(np.sqrt(np.mean(err[idx] ** 2))),
                    "mean_target": float(test["target"].to_numpy()[idx].mean()),
                }
            )
    return rows


def evaluate(
    network: str = "grid4x4", data_dir: Path = DATA_DIR, out_dir: Path = SUMMARY_DIR
) -> Path:
    data = pd.read_csv(data_dir / f"inflow_{network}.csv")
    feats = make_features(data)
    rows = []
    split = round(2 * (data["minute"].max() + 1) / 3)
    train = feats[feats["minute"] + HORIZON < split]
    test = feats[feats["minute"] >= split]
    rows += _scores(test, predict_all(train, test), "chronological")
    seeds = sorted(feats["seed"].unique())
    if len(seeds) >= 2:
        held = seeds[len(seeds) // 2 :]
        train = feats[~feats["seed"].isin(held)]
        test = feats[feats["seed"].isin(held)]
        rows += _scores(test, predict_all(train, test), "held-out seeds")
    out = out_dir / f"forecast_{network}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out
