"""agents/emergency_rl.py
Episode-level RL for the emergency-vehicle priority decision (M4).
Owner: Amen Allah Ben Aissa.

Each (ambulance, upcoming light) pair is one decision episode: when the
ambulance first comes within DECISION_RANGE_M of a light, one strategy is
chosen from STRATEGY_NAMES and applied until the ambulance passes. Reward:

    -(EV waiting seconds at the light + CIVILIAN_WEIGHT * civilian wait-seconds)

The policy is a set of per-action value regressors trained offline by fitted
Q-iteration (see experiments/train_ev_rl.py). With no policy loaded, the
controller explores uniformly at random (used to collect training data).
"""

import os
import random

import joblib
import pandas as pd

from forecasting.ev_arrival_predictor import (FEATURE_COLUMNS, extract_ev_features)
from agents.emergency_priority import axis_from_link

DECISION_RANGE_M = 300.0
CIVILIAN_WEIGHT = float(os.environ.get("EV_RL_CIV_WEIGHT", "0.25"))
DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "forecasting", "artifacts", "ev_rl_policy.joblib")

STRATEGY_NAMES = ["none", "dist_100", "dist_150", "dist_250", "eta_8", "eta_15"]
ACTIONS = list(range(len(STRATEGY_NAMES)))


def strategy_fires(action: int, distance: float, eta) -> bool:
    if action == 0:
        return False
    if action == 1:
        return distance <= 100
    if action == 2:
        return distance <= 150
    if action == 3:
        return distance <= 250
    if action == 4:
        return eta is not None and eta <= 8
    if action == 5:
        return eta is not None and eta <= 15
    return False


class EVRLPolicy:
    """Joint value model Q(state, strategy) with a safety margin: deviate from
    the reference strategy only when predicted reward beats it by `margin`."""

    def __init__(self, model=None, actions=None, margin: float = 0.0, reference_action: int = 2):
        self.model = model
        self.actions = actions if actions is not None else ACTIONS
        self.margin = margin
        self.reference_action = reference_action

    def q_values(self, features: dict) -> dict:
        x = pd.DataFrame([
            {**{key: features[key] for key in FEATURE_COLUMNS}, "action_feat": action}
            for action in self.actions
        ])
        return {action: float(value)
                for action, value in zip(self.actions, self.model.predict(x))}

    def select_action(self, features: dict) -> int:
        if self.model is None:
            return self.reference_action
        q = self.q_values(features)
        best = max(q, key=q.get)
        ref_value = q.get(self.reference_action, float("-inf"))
        if q[best] >= ref_value + self.margin:
            return best
        return self.reference_action

    def save(self, path: str = DEFAULT_POLICY_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"model": self.model, "actions": self.actions,
                     "strategies": STRATEGY_NAMES, "margin": self.margin,
                     "reference_action": self.reference_action}, path)
        print(f"[ev_rl] policy saved to {path} (margin={self.margin})")

    def load(self, path: str = DEFAULT_POLICY_PATH):
        data = joblib.load(path)
        self.model = data["model"]
        self.actions = data.get("actions", ACTIONS)
        self.margin = data.get("margin", 0.0)
        self.reference_action = data.get("reference_action", 2)
        return self


class EVRLController:
    """Manages decision episodes and turns them into traffic-light actions."""

    def __init__(self, fallback_policy, predictor=None, policy=None,
                 epsilon: float = 1.0, run_tag: str = "", seed: int = 12345):
        self.fallback_policy = fallback_policy
        self.predictor = predictor
        self.policy = policy
        self.epsilon = epsilon
        self.run_tag = run_tag
        self.rng = random.Random(seed)
        self.active = {}
        self.decided = set()
        self.episodes = []

    def _choose_action(self, features: dict) -> int:
        if self.policy is None or self.rng.random() < self.epsilon:
            return self.rng.choice(ACTIONS)
        return self.policy.select_action(features)

    def _close(self, key, sim_time):
        episode = self.active.pop(key)
        mean_civ = episode["civ_sum"] / max(episode["steps"], 1)
        reward = -(episode["ev_delay"] + CIVILIAN_WEIGHT * episode["civ_sum"])
        row = {"run_tag": self.run_tag, "ev_id": key[0], "tls_id": key[1],
               "action": episode["action"], "strategy": STRATEGY_NAMES[episode["action"]],
               "duration_s": round(sim_time - episode["start"], 2),
               "ev_delay_s": episode["ev_delay"],
               "civilian_wait_mean_s": round(mean_civ, 3),
               "reward": round(reward, 3)}
        row.update({feat: episode["features"][feat] for feat in FEATURE_COLUMNS})
        self.episodes.append(row)

    def _eta_for(self, traci, ev_id, light_id, upcoming):
        if self.predictor is None:
            return None
        rank = [entry[0] for entry in upcoming].index(light_id) + 1
        features = extract_ev_features(traci, ev_id, light_id, rank)
        if features is None:
            return None
        try:
            return self.predictor.predict(features)
        except Exception:
            return None

    def act(self, traci, states: dict) -> dict:
        sim_time = traci.simulation.getTime()
        actions = {tls: self.fallback_policy(state) for tls, state in states.items()}

        veh_ids = traci.vehicle.getIDList()
        ev_ids = [v for v in veh_ids if traci.vehicle.getVehicleClass(v) == "emergency"]
        civ_ids = [v for v in veh_ids if v not in ev_ids]
        civ_wait = (sum(traci.vehicle.getWaitingTime(v) for v in civ_ids)
                    / len(civ_ids)) if civ_ids else 0.0

        requests = []
        for key in list(self.active):
            ev_id, light_id = key
            episode = self.active[key]
            if ev_id not in veh_ids:
                self._close(key, sim_time)
                continue
            upcoming = traci.vehicle.getNextTLS(ev_id)
            entry = next((e for e in upcoming if e[0] == light_id), None)
            if entry is None:
                self._close(key, sim_time)
                continue
            episode["steps"] += 1
            episode["civ_sum"] += civ_wait
            if traci.vehicle.getSpeed(ev_id) < 0.1:
                episode["ev_delay"] += 1
            distance = entry[2]
            eta = (self._eta_for(traci, ev_id, light_id, upcoming)
                   if episode["action"] in (4, 5) else None)
            if strategy_fires(episode["action"], distance, eta):
                axis = axis_from_link(light_id, entry[1])
                if axis is not None:
                    requests.append((distance, light_id, axis))

        for ev_id in ev_ids:
            upcoming = traci.vehicle.getNextTLS(ev_id)
            for rank, (light_id, _, distance, _) in enumerate(upcoming, start=1):
                if distance > DECISION_RANGE_M:
                    break
                key = (ev_id, light_id)
                if key in self.active or key in self.decided:
                    continue
                features = extract_ev_features(traci, ev_id, light_id, rank)
                if features is None:
                    continue
                action = self._choose_action(features)
                self.active[key] = {"action": action, "features": features,
                                    "start": sim_time, "civ_sum": 0.0,
                                    "steps": 0, "ev_delay": 0}
                self.decided.add(key)

        served = set()
        for distance, light_id, axis in sorted(requests):
            if light_id in served:
                continue
            actions[light_id] = axis
            served.add(light_id)
        return actions

    def finish(self, sim_time=0.0):
        for key in list(self.active):
            self._close(key, sim_time)
        return self.episodes
