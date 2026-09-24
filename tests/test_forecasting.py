import numpy as np
import pandas as pd

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
