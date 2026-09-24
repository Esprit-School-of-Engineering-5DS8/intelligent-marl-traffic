"""Inflow forecast computed while the simulation runs (Tier 3: forecast in the observation).

Every decision, the forecaster counts the vehicles that appeared on the incoming lanes
of each approach since the previous decision (a detector at the start of the approach
would count the same vehicles), aggregates them per minute, and applies the Ridge model
fitted offline (``python -m cotraffic forecast``) to predict the arrivals of the next
5 minutes. The environment adds the prediction, per side, to the observation.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

from cotraffic.forecasting.dataset import DATA_DIR
from cotraffic.forecasting.models import FEATURES, LAGS, make_features


def export_ridge(network: str, data_dir: Path = DATA_DIR) -> Path:
    """Fit the Ridge model on the whole dataset and store its coefficients as JSON."""
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    data = pd.read_csv(data_dir / f"inflow_{network}.csv")
    feats = make_features(data.drop(columns="demand_end_minute", errors="ignore"))
    scaler = StandardScaler().fit(feats[FEATURES])
    model = Ridge(alpha=1.0).fit(scaler.transform(feats[FEATURES]), feats["target"])
    out = data_dir / f"ridge_{network}.json"
    out.write_text(
        json.dumps(
            {
                "features": FEATURES,
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
                "coef": model.coef_.tolist(),
                "intercept": float(model.intercept_),
                "rows": len(feats),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


class OnlineForecaster:
    def __init__(self, model_file: Path):
        m = json.loads(Path(model_file).read_text(encoding="utf-8"))
        self.mean = np.asarray(m["mean"])
        self.scale = np.asarray(m["scale"])
        self.coef = np.asarray(m["coef"])
        self.intercept = float(m["intercept"])
        self.reset()

    def reset(self) -> None:
        self.seen: dict[tuple[str, str], set[str]] = {}
        self.minute_counts: dict[tuple[str, str], deque] = defaultdict(
            lambda: deque([0.0] * LAGS, maxlen=LAGS)
        )
        self.current: dict[tuple[str, str], float] = defaultdict(float)
        self.minute = 0

    def _observe(self, env) -> None:
        minute = int(env.now // 60)
        if minute != self.minute:
            keys = set(self.current) | set(self.minute_counts)
            for _ in range(minute - self.minute):
                for key in keys:
                    self.minute_counts[key].append(self.current.get(key, 0.0))
                self.current = defaultdict(float)
            self.minute = minute
        for tid, inter in env.intersections.items():
            for side, lanes in inter.side_lanes.items():
                if not lanes:
                    continue
                # union over the lanes of the approach: a lane change is not an arrival
                ids = set().union(*(env.conn.lane.getLastStepVehicleIDs(ln) for ln in lanes))
                key = (tid, side)
                self.current[key] += len(ids - self.seen.get(key, set()))
                self.seen[key] = ids

    def predict(self, env) -> dict[str, dict[str, float]]:
        """Predicted arrivals of the next 5 minutes, per intersection and side."""
        if env.now < 1.0:
            self.reset()
        self._observe(env)
        hour_phase = (env.now - env.episode.measure_from) / 3600.0
        out: dict[str, dict[str, float]] = defaultdict(dict)
        for (tid, side), counts in self.minute_counts.items():
            lags = list(counts)[::-1]  # lag0 = the last complete minute
            x = (np.asarray(lags + [hour_phase]) - self.mean) / self.scale
            out[tid][side] = max(0.0, float(x @ self.coef + self.intercept))
        return out


def attach_forecaster(env, network: str) -> None:
    """Give ``env`` an online forecaster if its observation includes the forecast block."""
    if not env.obs_cfg.forecast:
        return
    model = DATA_DIR / f"ridge_{network}.json"
    if not model.is_file():
        raise FileNotFoundError(
            f"{model} missing: run `python -m cotraffic forecast --net {network}`"
        )
    env.forecaster = OnlineForecaster(model)
