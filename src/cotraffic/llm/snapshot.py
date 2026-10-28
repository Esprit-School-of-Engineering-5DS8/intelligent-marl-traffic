"""Save and restore a running episode, to replay one situation under several advices.

A snapshot is SUMO's state (with its random generators and pedestrians) plus the Python
state of the environment that SUMO does not hold: signal timers, measurements, reward
memory, perturbations (sensor faults, message loss), counters and the environment's own
random generator. Two restorations of the same snapshot step on identically
(tests/test_llm_snapshot.py), which is what makes short rollouts comparable with each other.
They do not reproduce the uninterrupted episode: with SUMO 1.27.1, a restored run leaves it
within the first minute, even from a snapshot taken right after the reset (a few % of
cumulated halting after 600 s on grid4x4, whatever --save-state.precision).
"""

from __future__ import annotations

import copy
import pickle
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# SUMO must be started with these options for snapshots to be exact
SUMO_STATE_OPTIONS = [
    "--save-state.rng",
    "true",
    "--save-state.transportables",
    "true",
    "--save-state.precision",
    "6",
]

_INTERSECTION_FIELDS = ("phase", "next_phase", "yellow_left", "green_since", "link_last_green")
_ENV_FIELDS = (
    "now",
    "stats",
    "decisions",
    "episode_reward",
    "halting_sum",
    "decision_steps",
    "teleports",
    "teleported",
    "ev_ids",
    "bus_ids",
    "person_ids",
    "ped_waiting",
    "ev_info",
    "bus_load",
    "runtime",
)


@dataclass
class Snapshot:
    time: float
    sumo_state: Path
    python_state: Path

    def save_obs(self, obs: dict[str, Any]) -> None:
        state = self._load()
        state["obs"] = obs
        self.python_state.write_bytes(pickle.dumps(state))

    def _load(self) -> dict[str, Any]:
        return pickle.loads(self.python_state.read_bytes())


def take(env, folder: Path, name: str, obs: dict[str, Any] | None = None) -> Snapshot:
    """Snapshot ``env`` between two steps (``obs`` = the observation of the next step)."""
    folder.mkdir(parents=True, exist_ok=True)
    sumo_file = folder / f"{name}.xml.gz"
    env.conn.simulation.saveState(str(sumo_file))
    meas = env.meas
    fields = {k: copy.deepcopy(getattr(env, k)) for k in _ENV_FIELDS if hasattr(env, k)}
    # nested defaultdict built with a lambda: stored as plain dicts
    fields["bus_load"] = {k: dict(v) for k, v in getattr(env, "bus_load", {}).items()}
    state = {
        "env": fields,
        "meas": {k: dict(getattr(meas, k)) for k in ("halting", "count", "speed")},
        "intersections": {
            tid: {k: copy.deepcopy(getattr(inter, k)) for k in _INTERSECTION_FIELDS}
            for tid, inter in env.intersections.items()
        },
        "rewards": copy.deepcopy(env.rewards.state),
        "rng": env._rng.bit_generator.state,
        # signals are driven with setRedYellowGreenState: their state is put back explicitly
        "signals": {
            tid: env.conn.trafficlight.getRedYellowGreenState(tid) for tid in env.intersections
        },
        "obs": obs,
    }
    py_file = folder / f"{name}.pkl"
    py_file.write_bytes(pickle.dumps(state))
    return Snapshot(time=float(env.now), sumo_state=sumo_file, python_state=py_file)


def restore(env, snap: Snapshot) -> dict[str, Any] | None:
    """Put ``env`` (already reset on the same episode) back to ``snap``; returns the
    observation that was current at that moment."""
    env.conn.simulation.loadState(str(snap.sumo_state))
    state = snap._load()
    for k, v in state["env"].items():
        setattr(env, k, copy.deepcopy(v))
    env.bus_load = defaultdict(
        lambda: defaultdict(float),
        {k: defaultdict(float, v) for k, v in state["env"].get("bus_load", {}).items()},
    )
    for k, v in state["meas"].items():
        getattr(env.meas, k).update(v)
    for tid, fields in state["intersections"].items():
        inter = env.intersections[tid]
        for k, v in fields.items():
            setattr(inter, k, copy.deepcopy(v))
    env.rewards.state = copy.deepcopy(state["rewards"])
    env._rng.bit_generator.state = state["rng"]
    for tid, signal in state["signals"].items():
        env.conn.trafficlight.setRedYellowGreenState(tid, signal)
    env.agents = list(env.possible_agents)
    return state["obs"]
