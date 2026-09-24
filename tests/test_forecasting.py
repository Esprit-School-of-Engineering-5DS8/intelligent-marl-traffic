import numpy as np
import pandas as pd
import pytest

from cotraffic.forecasting.models import HORIZON, LAGS, make_features, predict_all


def synthetic(n_minutes=60, seeds=(0, 1)):
    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for minute in range(n_minutes):
            rows.append(
                {
                    "network": "g",
                    "demand": "peak",
                    "seed": seed,
                    "tls": "A0",
                    "side": "west",
                    "minute": minute,
                    "vehicles": float(minute % 7 + rng.integers(0, 2)),
                }
            )
    return pd.DataFrame(rows)


def test_features_use_only_the_past_and_target_is_the_next_five_minutes():
    df = synthetic()
    feats = make_features(df)
    series = df[df["seed"] == 0].set_index("minute")["vehicles"]
    row = feats[(feats["seed"] == 0) & (feats["minute"] == 30)].iloc[0]
    for k in range(LAGS):
        assert row[f"lag{k}"] == series[30 - k]
    assert row["target"] == sum(series[31 + k] for k in range(HORIZON))
    # rows need a full lag window and a full horizon
    assert feats["minute"].min() == LAGS - 1
    assert feats["minute"].max() == 60 - HORIZON - 1


def test_models_beat_nothing_on_a_learnable_pattern():
    feats = make_features(synthetic(200, seeds=(0, 1, 2)))
    train, test = feats[feats["seed"] < 2], feats[feats["seed"] == 2]
    preds = predict_all(train, test)
    mae = {k: float(np.mean(np.abs(v - test["target"]))) for k, v in preds.items()}
    assert set(mae) == {
        "persistence (last 5 min)",
        "moving average (last 10 min)",
        "ridge regression",
        "gradient boosting",
    }
    assert mae["gradient boosting"] < mae["moving average (last 10 min)"]
    assert all(np.isfinite(list(mae.values())))


def test_sentence_describes_the_decision():
    from cotraffic.explainability.explain import sentence

    state = {
        "phase": 0,
        "queues": {0: 12.0, 1: 4.0},
        "names": {0: "north-south", 1: "east-west"},
        "ev": ("south", 180.0),
        "peds": 3.0,
    }
    text = sentence(state, 1, "")
    assert text.startswith("switches to east-west green")
    assert "12 halting on north-south" in text and "emergency vehicle 180 m from the south" in text
    assert "3 pedestrians waiting" in text
    assert sentence(state, 0, "min_green").endswith("shield: min green")


def test_online_forecaster_counts_arrivals_per_approach(tmp_path):
    import json
    from types import SimpleNamespace

    from cotraffic.forecasting.models import FEATURES
    from cotraffic.forecasting.online import OnlineForecaster

    # model predicting 5 x lag0: easy to check by hand
    model = {
        "features": FEATURES,
        "mean": [0.0] * len(FEATURES),
        "scale": [1.0] * len(FEATURES),
        "coef": [5.0] + [0.0] * (len(FEATURES) - 1),
        "intercept": 0.0,
    }
    path = tmp_path / "ridge.json"
    path.write_text(json.dumps(model))
    lanes = {"w_1": [], "w_2": []}
    conn = SimpleNamespace(lane=SimpleNamespace(getLastStepVehicleIDs=lambda ln: lanes[ln]))
    inter = SimpleNamespace(side_lanes={"west": ["w_1", "w_2"], "north": []})
    env = SimpleNamespace(
        conn=conn, intersections={"J": inter}, now=0.0, episode=SimpleNamespace(measure_from=0.0)
    )
    f = OnlineForecaster(path)
    f.predict(env)
    lanes["w_1"] = ["a", "b"]
    env.now = 30.0
    f.predict(env)
    lanes["w_1"], lanes["w_2"] = ["b"], ["a", "c"]  # a changed lane, c is new
    env.now = 55.0
    f.predict(env)
    env.now = 65.0  # minute 0 is complete: 3 arrivals (a, b, c)
    out = f.predict(env)
    assert out["J"]["west"] == pytest.approx(15.0)
