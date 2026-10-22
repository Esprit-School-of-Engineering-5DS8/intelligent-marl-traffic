"""Short-term inflow forecasting: next 5 minutes of arrivals on each approach.

Features at the end of minute t use only the past: the counts of minutes t-9..t and the
position of t in the demand hour. Target: vehicles arriving during minutes t+1..t+5.

Two splits, both free of leakage:

* chronological (main): models are fitted on the first two thirds of the demand period of
  every run and tested on the last third - forecasting the future of a known day;

Only minutes whose 5-minute target lies inside the demand period are used: after it, the
simulation's cool-down stops all new demand, which never happens on a real street.
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
from cotraffic.forecasting.features import (  # noqa: F401 (re-exported)
    FEATURES,
    HORIZON,
    LAGS,
    SERIES,
    make_features,
)
from cotraffic.paths import SUMMARY_DIR


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
    if "demand_end_minute" not in data:  # datasets recorded with the evaluation protocol
        ev = config.load_protocol()["evaluation"]
        data["demand_end_minute"] = (float(ev["warmup_s"]) + float(ev["measure_s"])) / 60.0
    demand_end = float(data["demand_end_minute"].min())
    feats = make_features(data.drop(columns="demand_end_minute"))
    feats = feats[feats["minute"] + HORIZON < demand_end].reset_index(drop=True)
    rows = []
    split = round(2 * demand_end / 3)
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
