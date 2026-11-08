"""Live wiring check for the per-scenario trained model path.

This reproduces what Settings -> Models does when you pin trained weights for one network
and then start that scenario, using the backing libraries directly (no server needed):

- PUT /api/policy          -> policy.update(method, network, checkpoint)
- GET /api/policy          -> policy.current() per-network readiness
- GET /api/models          -> registered registry (results/models.json)
- POST /api/simulation/start -> session.start(...), which reads the network's own method
- session._events          -> the modelLoaded event that says which weights ran

Run it from the repo root:  python scripts/live_wiring_check.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api.policy as policy
import api.routes.models as models
from api.simulation import session

RESULTS = ROOT / "results"
CHECKPOINT_SEED1 = RESULTS / "checkpoints" / "generalist" / "sf_mission_3x3" / "seed1.zip"
CHECKPOINT_SEED2 = RESULTS / "checkpoints" / "generalist" / "sf_mission_3x3" / "seed2.zip"

NETWORK = "sf_mission_3x3"
METHOD = "generalist"
SCENARIO = "grid-3x3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict[str, Any]:
    report: dict[str, Any] = {"steps": [], "errors": []}

    def note(title: str, payload: object = None) -> None:
        report["steps"].append({"title": title, "payload": payload})

    def fail(title: str, error: BaseException | str) -> None:
        report["errors"].append({"title": title, "error": repr(error)})

    # --- 1. artifacts exist ---------------------------------------------------
    for label, path in (("seed1", CHECKPOINT_SEED1), ("seed2", CHECKPOINT_SEED2)):
        if not path.is_file():
            fail(f"{label} checkpoint missing", path.as_posix())
            return report
    note(
        "checkpoint artifacts",
        {
            "seed1": {"path": CHECKPOINT_SEED1.as_posix(), "sha256": sha256(CHECKPOINT_SEED1)},
            "seed2": {"path": CHECKPOINT_SEED2.as_posix(), "sha256": sha256(CHECKPOINT_SEED2)},
        },
    )

    # --- 2. select seed1 for sf_mission_3x3 (PUT /api/policy) -----------------
    before = next(row for row in policy.current()["perNetwork"] if row["network"] == NETWORK)
    note("perNetwork before selection", before)
    try:
        policy.update(METHOD, NETWORK, checkpoint=CHECKPOINT_SEED1.as_posix())
    except Exception as error:
        fail("PUT /api/policy (select seed1)", error)
        return report

    after = next(row for row in policy.current()["perNetwork"] if row["network"] == NETWORK)
    note("perNetwork after selection", after)
    if after.get("method") != METHOD:
        fail("selected method not persisted", after.get("method"))
    if Path(str(after.get("checkpoint") or "")).name != CHECKPOINT_SEED1.name:
        fail("selected checkpoint not persisted", after.get("checkpoint"))
    if not after.get("available"):
        fail("selected checkpoint reported unavailable", after.get("reason"))

    # --- 3. the registered model points at the same weights -------------------
    registry = models.load_registry()
    note("registry names", list(registry.get("models", {}).keys()))
    seed1_entry = next(
        (v for v in registry.get("models", {}).get(METHOD, []) if v.get("runId") == f"{METHOD}|{NETWORK}|1"),
        None,
    )
    note("registry seed1 entry", seed1_entry)
    if seed1_entry is None:
        fail("seed1 registry entry missing", "no version for seed1")
    else:
        registered = ROOT / str(seed1_entry.get("checkpoint") or "")
        if not registered.is_file():
            fail("registered checkpoint file missing", registered.as_posix())
        elif sha256(registered) != sha256(CHECKPOINT_SEED1):
            fail("registered checkpoint is different weights", registered.as_posix())
        else:
            note("registered checkpoint matches seed1 weights by sha256", registered.as_posix())

    # --- 4. start the scenario: it must use this network's controller ---------
    try:
        snapshot = session.start(SCENARIO, speed=1)
    except Exception as error:
        fail("POST /api/simulation/start (trained seed1)", error)
        return report
    note("simulation.start", {k: snapshot.get(k) for k in ("runId", "status", "scenario", "network", "method", "policy")})

    if snapshot.get("network") != NETWORK:
        fail("run used the wrong network", snapshot.get("network"))
    if snapshot.get("method") != METHOD:
        fail("run used the wrong method", snapshot.get("method"))

    # --- 5. the run says which weights it loaded ------------------------------
    # The event is published once the SUMO environment is up, which takes a few seconds.
    deadline = time.time() + 90
    loaded: list[dict[str, Any]] = []
    while time.time() < deadline:
        loaded = [e for e in list(getattr(session, "_events", [])) if e.get("kind") == "modelLoaded"]
        if loaded or session.snapshot().get("status") in ("idle", "error"):
            break
        time.sleep(0.5)
    note("modelLoaded events", loaded)
    if not any(
        e.get("detail", {}).get("method") == METHOD
        and e.get("detail", {}).get("network") == NETWORK
        and e.get("detail", {}).get("checkpoint") == CHECKPOINT_SEED1.name
        for e in loaded
    ):
        fail("no modelLoaded event for the trained seed1 weights", [e.get("detail") for e in loaded])

    # --- 6. the snapshot agrees about status and weights ----------------------
    with session.lock:
        status = session.state.get("status")
        run_policy = dict(session.state.get("policy") or {})
    note("run status at check time", status)
    if status not in ("running", "starting"):
        fail("run did not start", status)
    if Path(str(run_policy.get("checkpoint") or "")).name != CHECKPOINT_SEED1.name:
        fail("run snapshot reports different weights", run_policy)

    # --- 7. stop and restore the pre-run selection ----------------------------
    try:
        session.stop()
        note("simulation.stop returned idle", session.snapshot().get("status"))
    except Exception as error:
        fail("simulation.stop", error)

    try:
        policy.update(before.get("method") or "mp", NETWORK, checkpoint=before.get("checkpoint") or "auto")
        note("restored sf_mission_3x3 controller", policy.scenario(NETWORK))
    except Exception as error:
        fail("restore previous selection", error)

    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if not report.get("errors") else 1)
