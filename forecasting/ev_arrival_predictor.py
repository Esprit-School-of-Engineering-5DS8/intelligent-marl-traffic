"""forecasting/ev_arrival_predictor.py
ETA prediction + red-arrival classifier for emergency vehicles (E2).
Owner: Amen Allah Ben Aissa.

Predicts, for an ambulance and one of its upcoming traffic lights:
- seconds until it passes that light (regression)
- probability it arrives on a non-green light (classification)

Feature extraction lives here and is shared by the experiment driver and the
policy, so training and inference cannot drift apart.

Train:
    python forecasting/ev_arrival_predictor.py --data "results/ev/3x3_*_eta.csv"
"""

import os
import glob
import argparse

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.metrics import (mean_absolute_error, mean_squared_error, roc_auc_score,
                             precision_recall_fscore_support)

FEATURE_COLUMNS = [
    "distance_m", "speed_m_s", "accel_m_s2", "leader_gap_m", "lane_vehicles",
    "signal_state", "time_to_switch_s", "time_in_phase_s", "turn",
    "first_distance_m", "first_signal_state", "first_time_to_switch_s",
]

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "artifacts", "ev_eta.joblib")
DEFAULT_RED_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "artifacts", "ev_red.joblib")

_CONTROLLED_LINKS = {}


def link_signal_char(link_index, signal_field):
    """State of the vehicle's link at a TLS. SUMO 1.28 returns a single char;
    older interface variants return the full phase string."""
    if len(signal_field) == 1:
        return signal_field
    if 0 <= link_index < len(signal_field):
        return signal_field[link_index]
    return "r"


def _signal_state(char):
    return 2 if char in ("G", "g") else (1 if char in ("y", "Y") else 0)


def _axis(edge_id):
    if "top" in edge_id or "bottom" in edge_id:
        return 0
    if "left" in edge_id or "right" in edge_id:
        return 1
    return 0 if edge_id[0] == edge_id[2] else 1


def _is_turn(traci, tls_id, link_index):
    if tls_id not in _CONTROLLED_LINKS:
        _CONTROLLED_LINKS[tls_id] = traci.trafficlight.getControlledLinks(tls_id)
    links = _CONTROLLED_LINKS[tls_id]
    if 0 <= link_index < len(links) and links[link_index]:
        incoming = links[link_index][0][0].rsplit("_", 1)[0]
        outgoing = links[link_index][0][1].rsplit("_", 1)[0]
        return 1 if _axis(incoming) != _axis(outgoing) else 0
    return 0


def _phase_times(traci, tls_id, sim_time):
    try:
        next_switch = traci.trafficlight.getNextSwitch(tls_id)
        duration = traci.trafficlight.getPhaseDuration(tls_id)
        return max(0.0, next_switch - sim_time), sim_time - (next_switch - duration)
    except Exception:
        return -1.0, -1.0


def extract_ev_features(traci, veh_id, target_light, rank):
    """Features for one (ambulance, upcoming light) pair. `rank` is 1-based in
    the ambulance route; rank >= 2 rows also carry the first light's state."""
    upcoming = traci.vehicle.getNextTLS(veh_id)
    if not upcoming or rank > len(upcoming):
        return None
    light_id, link_index, distance, signal_field = upcoming[rank - 1]
    if light_id != target_light:
        return None
    sim_time = traci.simulation.getTime()
    char = link_signal_char(link_index, signal_field)
    first_tls, first_index, first_distance, first_field = upcoming[0]
    first_tts, _ = _phase_times(traci, first_tls, sim_time)
    tts, elapsed = _phase_times(traci, light_id, sim_time)
    leader = traci.vehicle.getLeader(veh_id)
    return {
        "distance_m": distance,
        "speed_m_s": traci.vehicle.getSpeed(veh_id),
        "accel_m_s2": traci.vehicle.getAcceleration(veh_id),
        "leader_gap_m": min(leader[1], 500.0) if leader is not None else 500.0,
        "lane_vehicles": traci.lane.getLastStepVehicleNumber(traci.vehicle.getLaneID(veh_id)),
        "signal_state": _signal_state(char),
        "time_to_switch_s": tts,
        "time_in_phase_s": elapsed,
        "turn": _is_turn(traci, light_id, link_index),
        "first_distance_m": first_distance,
        "first_signal_state": _signal_state(link_signal_char(first_index, first_field)),
        "first_time_to_switch_s": first_tts,
    }


def physics_eta(features) -> float:
    """Heuristic baseline for comparison: travel time plus red-light penalty."""
    eta = features["distance_m"] / max(features["speed_m_s"], 2.0)
    if features["signal_state"] == 0:
        eta += 3.0
    return eta


class EVArrivalPredictor:
    def __init__(self):
        self.model = None
        self.red_model = None

    def fit(self, df: pd.DataFrame):
        self.model = GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.05,
            subsample=0.8, random_state=42)
        self.model.fit(df[FEATURE_COLUMNS], df["label_s"])
        if "arrive_red" in df.columns and df["arrive_red"].nunique() > 1:
            self.red_model = GradientBoostingClassifier(
                n_estimators=300, max_depth=3, learning_rate=0.05,
                subsample=0.8, random_state=42)
            self.red_model.fit(df[FEATURE_COLUMNS], df["arrive_red"])
        return self

    def predict(self, features: dict) -> float:
        if self.model is None:
            raise RuntimeError("Regression model is not fitted or loaded")
        x = pd.DataFrame([{key: features[key] for key in FEATURE_COLUMNS}])
        return float(self.model.predict(x)[0])

    def predict_red_prob(self, features: dict) -> float:
        if self.red_model is None:
            raise RuntimeError("Red-arrival model is not fitted or loaded")
        x = pd.DataFrame([{key: features[key] for key in FEATURE_COLUMNS}])
        return float(self.red_model.predict_proba(x)[0][1])

    def save(self, path: str = DEFAULT_MODEL_PATH, red_path: str = DEFAULT_RED_MODEL_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.model, path)
        print(f"[ev_eta] ETA model saved to {path}")
        if self.red_model is not None:
            joblib.dump(self.red_model, red_path)
            print(f"[ev_eta] red-arrival model saved to {red_path}")

    def load(self, path: str = DEFAULT_MODEL_PATH, red_path: str = DEFAULT_RED_MODEL_PATH):
        self.model = joblib.load(path)
        try:
            self.red_model = joblib.load(red_path)
        except Exception:
            self.red_model = None
        return self


def load_dataset(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No ETA data files match '{pattern}'")
    print(f"[ev_eta] {len(files)} data files")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def regression_metrics(df: pd.DataFrame, predictor: EVArrivalPredictor) -> dict:
    pred = predictor.model.predict(df[FEATURE_COLUMNS])
    err = np.abs(pred - df["label_s"].to_numpy())
    result = {"model_all_mae": round(err.mean(), 2),
              "model_all_rmse": round(mean_squared_error(df["label_s"], pred) ** 0.5, 2)}
    for rank in (1, 2):
        mask = (df["rank"] == rank).to_numpy()
        if mask.any():
            result[f"model_rank{rank}_mae"] = round(err[mask].mean(), 2)
    return result


def classifier_metrics(df: pd.DataFrame, predictor: EVArrivalPredictor) -> dict:
    if predictor.red_model is None or "arrive_red" not in df.columns:
        return {}
    prob = predictor.red_model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
    y = df["arrive_red"].to_numpy()
    result = {}
    for rank in (1, 2):
        mask = (df["rank"] == rank).to_numpy()
        if mask.any() and len(set(y[mask])) > 1:
            result[f"red_auc_rank{rank}"] = round(roc_auc_score(y[mask], prob[mask]), 3)
    r1 = (df["rank"] == 1).to_numpy()
    far = r1 & (df["distance_m"] > 150).to_numpy()
    if far.any() and len(set(y[far])) > 1:
        result["red_auc_rank1_far"] = round(roc_auc_score(y[far], prob[far]), 3)
    if r1.any():
        precision, recall, _, _ = precision_recall_fscore_support(
            y[r1], (prob[r1] >= 0.5).astype(int), average="binary", zero_division=0)
        result["red_rank1_precision"] = round(precision, 3)
        result["red_rank1_recall"] = round(recall, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description="Train the EV ETA predictor and red-arrival classifier")
    parser.add_argument("--data", default="results/ev/3x3_*_eta.csv",
                        help="Glob pattern for ETA data files")
    parser.add_argument("--test-stride", type=int, default=4,
                        help="Hold out every Nth run (grouped by run_tag) for testing")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--red-model", default=DEFAULT_RED_MODEL_PATH)
    args = parser.parse_args()

    df = load_dataset(args.data)
    missing = [c for c in FEATURE_COLUMNS + ["label_s", "arrive_red"] if c not in df.columns]
    if missing:
        raise ValueError(f"Data is missing columns {missing} - recollect with --collect-eta")

    tags = sorted(df["run_tag"].unique())
    test_tags = tags[::args.test_stride]
    train = df[~df["run_tag"].isin(test_tags)]
    test = df[df["run_tag"].isin(test_tags)]
    print(f"[ev_eta] {len(df)} rows | train {len(train)} / {len(tags) - len(test_tags)} runs "
          f"| test {len(test)} / {len(test_tags)} runs")
    print(f"[ev_eta] held-out runs: {test_tags}")

    predictor = EVArrivalPredictor().fit(train)
    for key, value in {**regression_metrics(test, predictor),
                       **classifier_metrics(test, predictor)}.items():
        print(f"  {key:22}: {value}")
    predictor.save(args.model, args.red_model)


if __name__ == "__main__":
    main()
