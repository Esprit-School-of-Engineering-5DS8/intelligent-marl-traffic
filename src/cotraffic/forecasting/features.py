"""Forecasting features, shared by the offline models and the online forecaster.

Kept free of scikit-learn: the online forecaster runs inside the simulation process, and
scikit-learn imports pyarrow, whose DLLs clash with the Arrow library bundled in libsumo
when libsumo is loaded first.
"""

from __future__ import annotations

import pandas as pd

from cotraffic import config

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
